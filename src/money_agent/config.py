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
    starting_balance_cents: int = 10_000

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_path=Path(os.getenv("MONEY_AGENT_DB", "data/money_agent.db")),
            model=os.getenv("MONEY_AGENT_MODEL", "gpt-5.4"),
            max_turns=int(os.getenv("MONEY_AGENT_MAX_TURNS", "8")),
            research_max_queries=int(
                os.getenv("MONEY_AGENT_RESEARCH_MAX_QUERIES", "3")
            ),
            research_max_sources=int(
                os.getenv("MONEY_AGENT_RESEARCH_MAX_SOURCES", "12")
            ),
            research_stale_hours=int(
                os.getenv("MONEY_AGENT_RESEARCH_STALE_HOURS", "168")
            ),
        )
