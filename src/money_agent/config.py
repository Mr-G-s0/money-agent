from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path
    model: str
    max_turns: int
    research_max_queries: int
    research_max_sources: int
    research_stale_hours: int
    workspace_path: Path
    workspace_max_files: int
    workspace_max_bytes: int
    creation_max_files_per_run: int
    execution_max_attempts: int
    workspace_max_operations: int
    starting_balance_cents: int = 10_000

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_path=Path(os.getenv("MONEY_AGENT_DB", "data/money_agent.db")),
            model=os.getenv("MONEY_AGENT_MODEL", "gpt-5.4"),
            max_turns=int(os.getenv("MONEY_AGENT_MAX_TURNS", "8")),
            research_max_queries=int(os.getenv("MONEY_AGENT_RESEARCH_MAX_QUERIES", "3")),
            research_max_sources=int(os.getenv("MONEY_AGENT_RESEARCH_MAX_SOURCES", "12")),
            research_stale_hours=int(os.getenv("MONEY_AGENT_RESEARCH_STALE_HOURS", "168")),
            workspace_path=Path(os.getenv("MONEY_AGENT_WORKSPACE", "workspace")),
            workspace_max_files=int(os.getenv("MONEY_AGENT_WORKSPACE_MAX_FILES", "100")),
            workspace_max_bytes=int(os.getenv("MONEY_AGENT_WORKSPACE_MAX_BYTES", "1000000")),
            creation_max_files_per_run=int(os.getenv("MONEY_AGENT_CREATION_MAX_FILES", "6")),
            execution_max_attempts=int(os.getenv("MONEY_AGENT_EXECUTION_MAX_ATTEMPTS", "3")),
            workspace_max_operations=int(os.getenv("MONEY_AGENT_WORKSPACE_MAX_OPERATIONS", "30")),
        )
