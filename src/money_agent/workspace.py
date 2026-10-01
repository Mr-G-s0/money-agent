"""Capability-based local creation and deliberately narrow code validation."""

from __future__ import annotations

import ast
import csv
import errno
import io
import json
import os
import resource
import subprocess
import stat
import sys
import tempfile
import unicodedata
from contextlib import contextmanager
from urllib.parse import unquote
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from money_agent.storage import Database, utc_now


class WorkspaceViolation(ValueError):
    """Raised when a requested capability crosses the local sandbox boundary."""


@dataclass(frozen=True)
class WorkspaceLimits:
    max_files: int = 100
    max_bytes: int = 1_000_000
    max_files_per_run: int = 6
    max_execution_attempts: int = 3
    max_operations: int = 30
    max_path_depth: int = 12
    max_path_length: int = 240

    def __post_init__(self) -> None:
        if min(
            self.max_files,
            self.max_bytes,
            self.max_files_per_run,
            self.max_operations,
            self.max_path_depth,
            self.max_path_length,
        ) < 1:
            raise ValueError("workspace limits must be positive")
        if self.max_execution_attempts < 0:
            raise ValueError("execution attempts cannot be negative")


@dataclass(frozen=True)
class Artifact:
    id: int
    file_path: str
    artifact_type: str
    purpose: str
    opportunity: str
    created_at: str
    modified_at: str
    status: str
    evaluation_notes: str
    related_research_ids: list[int]


class ExecutionKind(StrEnum):
    PYTHON_COMPILE = "python_compile"
    RESTRICTED_PYTHON = "restricted_python"


@dataclass(frozen=True)
class ExecutionResult:
    success: bool
    kind: ExecutionKind
    output: str


_SENSITIVE_NAMES = {
    ".env",
    ".ssh",
    ".aws",
    ".gnupg",
    "credentials",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
    "known_hosts",
    "cookies",
    "login data",
    ".git-credentials",
    ".netrc",
    "passwd",
    "shadow",
    "web data",
    "local state",
}
_SENSITIVE_FRAGMENTS = (
    "api_key",
    "apikey",
    "api-key",
    "credential",
    "secret",
    "password",
    "token",
    "cookie",
    "browser",
    "profile",
    "id_rsa",
    "id_ed25519",
)
_ODD_SEPARATORS = {"∕", "⁄", "／", "⧵", "＼"}


class Workspace:
    """File API rooted at one directory; callers never receive a shell capability."""

    def __init__(self, root: Path | str, limits: WorkspaceLimits):
        self.root = Path(root).resolve()
        forbidden_roots = {Path("/").resolve(), Path.home().resolve(), Path.cwd().resolve()}
        forbidden_roots.update(
            Path(item).resolve()
            for item in ("/etc", "/usr", "/var", "/root", "/boot", "/proc", "/sys")
        )
        if self.root in forbidden_roots:
            raise WorkspaceViolation("workspace root cannot be a system or user root")
        self.limits = limits
        self.files_created_this_run = 0
        self.execution_attempts = 0
        self.operations = 0
        self.root.mkdir(parents=True, exist_ok=True)

    def _parts(self, relative: str | Path) -> tuple[str, ...]:
        text = str(relative)
        normalized = unicodedata.normalize("NFKC", text)
        decoded = unquote(normalized)
        if (
            decoded != normalized
            or normalized != text
            or any(char in text for char in _ODD_SEPARATORS)
        ):
            raise WorkspaceViolation("encoded or noncanonical path characters are forbidden")
        if (
            not text
            or len(text) > self.limits.max_path_length
            or text.startswith(("/", "~", "\\"))
            or "\\" in text
            or ":" in text
            or "\x00" in text
            or "/./" in text
            or text.startswith("./")
            or text.endswith("/.")
        ):
            raise WorkspaceViolation("path must be an unambiguous relative path")
        raw = Path(text)
        if raw.is_absolute() or not raw.parts or any(part in {".", ".."} for part in raw.parts):
            raise WorkspaceViolation("path must be relative and cannot traverse directories")
        if len(raw.parts) > self.limits.max_path_depth:
            raise WorkspaceViolation("path-depth limit exceeded")
        if any(part != part.strip() or not part for part in raw.parts):
            raise WorkspaceViolation("path components cannot have surrounding whitespace")
        if any(
            part.lower() in _SENSITIVE_NAMES
            or part.lower().startswith(".env")
            or any(extension in {"pem", "key"} for extension in part.lower().split("."))
            or any(fragment in part.lower() for fragment in _SENSITIVE_FRAGMENTS)
            for part in raw.parts
        ):
            raise WorkspaceViolation("sensitive files are not accessible")
        return raw.parts

    def _path(self, relative: str | Path) -> Path:
        raw = Path(*self._parts(relative))
        candidate = (self.root / raw).resolve(strict=False)
        if not candidate.is_relative_to(self.root):
            raise WorkspaceViolation("path escapes the workspace")
        # Existing parent symlinks are resolved above; ensure the final target is not a symlink.
        if candidate.is_symlink():
            raise WorkspaceViolation("symbolic links are not accessible")
        return candidate

    def _usage(self) -> tuple[int, int]:
        files = [item for item in self.root.rglob("*") if item.is_file() and not item.is_symlink()]
        return len(files), sum(item.stat().st_size for item in files)

    @contextmanager
    def _parent_fd(self, relative: str | Path, *, create: bool = False):
        """Walk parents using no-follow directory descriptors to close symlink races."""
        parts = self._parts(relative)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        descriptors = [os.open(self.root, flags)]
        try:
            for part in parts[:-1]:
                try:
                    descriptor = os.open(part, flags, dir_fd=descriptors[-1])
                except FileNotFoundError:
                    if not create:
                        raise
                    os.mkdir(part, mode=0o700, dir_fd=descriptors[-1])
                    descriptor = os.open(part, flags, dir_fd=descriptors[-1])
                descriptors.append(descriptor)
            yield descriptors[-1], parts[-1]
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                raise WorkspaceViolation("symbolic-link path components are forbidden") from exc
            raise
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    def write_text(self, relative: str, content: str, *, overwrite: bool = False) -> Path:
        self._operation()
        target = self._path(relative)
        count, size = self._usage()
        encoded = content.encode("utf-8")
        with self._parent_fd(relative, create=True) as (parent_fd, name):
            try:
                metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                exists = True
                if not stat.S_ISREG(metadata.st_mode):
                    raise WorkspaceViolation("target must be a regular non-symlink file")
                previous = metadata.st_size
            except FileNotFoundError:
                exists = False
                previous = 0
            if exists and not overwrite:
                raise FileExistsError(relative)
            if not exists and (
                count >= self.limits.max_files
                or self.files_created_this_run >= self.limits.max_files_per_run
            ):
                raise WorkspaceViolation("file-count limit exceeded")
            if size - previous + len(encoded) > self.limits.max_bytes:
                raise WorkspaceViolation("workspace-size limit exceeded")
            flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW
            flags |= os.O_TRUNC if overwrite else os.O_EXCL
            descriptor = os.open(name, flags, 0o600, dir_fd=parent_fd)
            try:
                with os.fdopen(descriptor, "wb", closefd=False) as stream:
                    stream.write(encoded)
            finally:
                os.close(descriptor)
        if not exists:
            self.files_created_this_run += 1
        return target

    def write_json(self, relative: str, value: object, *, overwrite: bool = False) -> Path:
        return self.write_text(
            relative, json.dumps(value, indent=2, sort_keys=True) + "\n", overwrite=overwrite
        )

    def write_csv(self, relative: str, rows: list[list[str]], *, overwrite: bool = False) -> Path:
        stream = io.StringIO(newline="")
        csv.writer(stream).writerows(rows)
        return self.write_text(relative, stream.getvalue(), overwrite=overwrite)

    def read_text(self, relative: str) -> str:
        self._operation()
        return self._read_text_unmetered(relative)

    def _read_text_unmetered(self, relative: str | Path) -> str:
        self._path(relative)
        with self._parent_fd(relative) as (parent_fd, name):
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
            try:
                metadata = os.fstat(descriptor)
                if not stat.S_ISREG(metadata.st_mode):
                    raise WorkspaceViolation("target must be a regular file")
                if metadata.st_size > self.limits.max_bytes:
                    raise WorkspaceViolation("file exceeds workspace-size limit")
                with os.fdopen(descriptor, "r", encoding="utf-8", closefd=False) as stream:
                    return stream.read(self.limits.max_bytes + 1)
            finally:
                os.close(descriptor)

    def execute(self, relative: str, kind: ExecutionKind) -> ExecutionResult:
        self._operation()
        if self.execution_attempts >= self.limits.max_execution_attempts:
            raise WorkspaceViolation("execution-attempt limit exceeded")
        self.execution_attempts += 1
        target = self._path(relative)
        if target.suffix != ".py" or not target.is_file():
            raise WorkspaceViolation("only workspace Python files may be checked")
        source = self._read_text_unmetered(relative)
        if len(source.encode("utf-8")) > 100_000:
            raise WorkspaceViolation("Python source exceeds the execution-size limit")
        try:
            tree = ast.parse(source, filename=relative)
            compile(tree, relative, "exec")
        except SyntaxError as exc:
            return ExecutionResult(False, kind, f"SyntaxError: {exc.msg} (line {exc.lineno})")
        if kind == ExecutionKind.PYTHON_COMPILE:
            return ExecutionResult(True, kind, "Python syntax compilation passed")
        self._validate_restricted_python(tree)
        command = [sys.executable, "-I", "-S", "-c", source]
        with tempfile.TemporaryFile() as output_file:
            try:
                completed = subprocess.run(
                    command,
                    cwd=self.root,
                    env={"PATH": os.defpath},
                    stdout=output_file,
                    stderr=subprocess.STDOUT,
                    timeout=2,
                    check=False,
                    preexec_fn=self._restrict_child_resources,
                )
            except subprocess.TimeoutExpired:
                return ExecutionResult(False, kind, "Execution timed out")
            output_file.seek(0)
            output = output_file.read(4001).decode("utf-8", errors="replace")
        if len(output) > 4000:
            output = output[:4000] + "\n[output truncated]"
        return ExecutionResult(completed.returncode == 0, kind, output)

    @staticmethod
    def _restrict_child_resources() -> None:
        """Apply defense-in-depth OS limits before the restricted child starts."""
        resource.setrlimit(resource.RLIMIT_CPU, (1, 1))
        resource.setrlimit(resource.RLIMIT_AS, (128 * 1024 * 1024, 128 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024, 64 * 1024))
        resource.setrlimit(resource.RLIMIT_NOFILE, (16, 16))

    def _operation(self) -> None:
        if self.operations >= self.limits.max_operations:
            raise WorkspaceViolation("workspace-operation limit exceeded")
        self.operations += 1

    @staticmethod
    def _validate_restricted_python(tree: ast.AST) -> None:
        forbidden = (
            ast.Import,
            ast.ImportFrom,
            ast.Attribute,
            ast.With,
            ast.Try,
            ast.Lambda,
            ast.ClassDef,
            ast.FunctionDef,
            ast.AsyncFunctionDef,
            ast.Delete,
            ast.Global,
            ast.Nonlocal,
            ast.While,
            ast.ListComp,
            ast.SetComp,
            ast.DictComp,
            ast.GeneratorExp,
            ast.Await,
            ast.Yield,
            ast.YieldFrom,
        )
        allowed_calls = {"print", "len", "range", "sum", "min", "max", "sorted", "enumerate"}
        nodes = list(ast.walk(tree))
        if len(nodes) > 5_000:
            raise WorkspaceViolation("restricted Python syntax is too complex")
        for node in nodes:
            if isinstance(node, forbidden):
                raise WorkspaceViolation(f"restricted Python forbids {type(node).__name__}")
            if isinstance(node, ast.Name) and node.id.startswith("__"):
                raise WorkspaceViolation("dunder access is forbidden")
            if isinstance(node, ast.Constant):
                if isinstance(node.value, int) and abs(node.value) > 1_000_000:
                    raise WorkspaceViolation("integer literal is too large")
                if isinstance(node.value, (str, bytes)) and len(node.value) > 10_000:
                    raise WorkspaceViolation("string literal is too large")
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
                raise WorkspaceViolation("exponentiation is forbidden")
            if isinstance(node, ast.Call) and (
                not isinstance(node.func, ast.Name) or node.func.id not in allowed_calls
            ):
                raise WorkspaceViolation("function call is not allowlisted")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "range"
                and any(
                    not isinstance(argument, ast.Constant)
                    or not isinstance(argument.value, int)
                    or abs(argument.value) > 10_000
                    for argument in node.args
                )
            ):
                raise WorkspaceViolation("range arguments must be bounded integer literals")


class ArtifactStore:
    def __init__(self, database: Database):
        self.database = database

    def upsert(
        self,
        *,
        file_path: str,
        artifact_type: str,
        purpose: str,
        opportunity: str,
        status: str,
        evaluation_notes: str,
        related_research_ids: list[int],
    ) -> Artifact:
        path = Path(file_path)
        if (
            path.is_absolute()
            or not path.parts
            or any(part in {".", ".."} for part in path.parts)
            or "\\" in file_path
            or ":" in file_path
            or unquote(file_path) != file_path
        ):
            raise WorkspaceViolation("artifact path must be workspace-relative")
        if status not in {"draft", "verified", "needs_work"}:
            raise ValueError("invalid artifact status")
        if any(not isinstance(item, int) or item < 1 for item in related_research_ids):
            raise ValueError("related research IDs must be positive integers")
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO artifacts(file_path, artifact_type, purpose, opportunity, created_at, "
                "modified_at, status, evaluation_notes, related_research_ids) VALUES(?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(file_path) DO UPDATE SET artifact_type=excluded.artifact_type, "
                "purpose=excluded.purpose, opportunity=excluded.opportunity, modified_at=excluded.modified_at, "
                "status=excluded.status, evaluation_notes=excluded.evaluation_notes, "
                "related_research_ids=excluded.related_research_ids",
                (
                    file_path,
                    artifact_type,
                    purpose,
                    opportunity,
                    now,
                    now,
                    status,
                    evaluation_notes,
                    json.dumps(related_research_ids),
                ),
            )
            row = connection.execute(
                "SELECT * FROM artifacts WHERE file_path=?", (file_path,)
            ).fetchone()
        if row is None:  # pragma: no cover
            raise RuntimeError("artifact was not persisted")
        return self._convert(dict(row))

    def for_opportunity(self, opportunity: str) -> list[Artifact]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM artifacts WHERE opportunity=? ORDER BY id", (opportunity,)
            ).fetchall()
        return [self._convert(dict(row)) for row in rows]

    @staticmethod
    def _convert(row: dict) -> Artifact:
        try:
            research_ids = json.loads(row["related_research_ids"])
        except (json.JSONDecodeError, TypeError):
            research_ids = []
        row["related_research_ids"] = (
            research_ids
            if isinstance(research_ids, list)
            and all(isinstance(item, int) and item > 0 for item in research_ids)
            else []
        )
        return Artifact(**row)
