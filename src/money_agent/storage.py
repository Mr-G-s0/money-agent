from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger_transactions (
  id INTEGER PRIMARY KEY,
  amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0),
  kind TEXT NOT NULL CHECK(kind IN ('expense', 'revenue')),
  status TEXT NOT NULL CHECK(status IN ('realized', 'pending', 'cancelled')),
  description TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
  id INTEGER PRIMARY KEY,
  action TEXT NOT NULL,
  action_kind TEXT NOT NULL,
  cost_cents INTEGER NOT NULL CHECK(cost_cents >= 0),
  reason TEXT NOT NULL,
  expected_upside TEXT NOT NULL,
  risks TEXT NOT NULL,
  cash_before_cents INTEGER NOT NULL,
  cash_after_cents INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected')),
  created_at TEXT NOT NULL,
  resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS memory (
  id INTEGER PRIMARY KEY,
  category TEXT NOT NULL,
  content TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS memory_category_idx ON memory(category, id);
CREATE TABLE IF NOT EXISTS research (
  id INTEGER PRIMARY KEY,
  query TEXT NOT NULL,
  source_url TEXT NOT NULL,
  source_title TEXT NOT NULL,
  retrieved_at TEXT NOT NULL,
  findings TEXT NOT NULL,
  opportunity TEXT NOT NULL,
  confidence TEXT NOT NULL CHECK(confidence IN ('low', 'medium', 'high')),
  evidence_status TEXT NOT NULL CHECK(evidence_status IN ('verified', 'inferred', 'uncertain')),
  fingerprint TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS research_query_idx ON research(query, retrieved_at);
CREATE TABLE IF NOT EXISTS research_runs (
  id INTEGER PRIMARY KEY,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  api_calls INTEGER NOT NULL DEFAULT 0,
  sources_saved INTEGER NOT NULL DEFAULT 0,
  cache_hits INTEGER NOT NULL DEFAULT 0,
  errors INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL CHECK(status IN ('running', 'completed', 'partial', 'failed'))
);
CREATE TABLE IF NOT EXISTS artifacts (
  id INTEGER PRIMARY KEY,
  file_path TEXT NOT NULL UNIQUE,
  artifact_type TEXT NOT NULL,
  purpose TEXT NOT NULL,
  opportunity TEXT NOT NULL,
  created_at TEXT NOT NULL,
  modified_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('draft', 'verified', 'needs_work')),
  evaluation_notes TEXT NOT NULL DEFAULT '',
  related_research_ids TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS artifacts_opportunity_idx ON artifacts(opportunity, id);
"""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, path: Path | str, starting_balance_cents: int = 10_000):
        self.path = Path(path)
        self.starting_balance_cents = starting_balance_cents

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            connection.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES ('starting_balance_cents', ?)",
                (str(self.starting_balance_cents),),
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def remember(self, category: str, content: str, metadata: dict | None = None) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO memory(category, content, metadata_json, created_at) VALUES (?, ?, ?, ?)",
                (
                    category,
                    content,
                    json.dumps(metadata or {}, sort_keys=True),
                    utc_now(),
                ),
            )
            if cursor.lastrowid is None:  # pragma: no cover - SQLite always provides this
                raise RuntimeError("SQLite did not return a memory ID")
            return cursor.lastrowid

    def memories(self, limit: int = 30) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT category, content, metadata_json, created_at FROM memory "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {**dict(row), "metadata": json.loads(row["metadata_json"])} for row in reversed(rows)
        ]
