from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from money_agent.storage import Database, utc_now

DISCOVERY_QUERIES = (
    "Current legitimate small business opportunities testable for 100 USD or less; identify customer demand and time to first revenue",
    "Current recurring customer problems suitable for a small digital product or productized service; include evidence of demand",
    "Current marketplace pricing, competitors, fees, and platform constraints for low-cost digital products and online services",
)


@dataclass(frozen=True)
class WebSource:
    url: str
    title: str


@dataclass(frozen=True)
class SearchResponse:
    findings: str
    sources: list[WebSource]


@dataclass(frozen=True)
class ResearchLimits:
    max_queries: int = 3
    max_sources: int = 12
    stale_after: timedelta = timedelta(days=7)

    def __post_init__(self) -> None:
        if (
            self.max_queries < 0
            or self.max_sources < 0
            or self.stale_after < timedelta(0)
        ):
            raise ValueError("research limits cannot be negative")


@dataclass(frozen=True)
class ResearchReport:
    records: list[dict]
    api_calls: int
    cache_hits: int
    errors: list[str]


class WebSearchProvider(Protocol):
    def search(self, query: str, max_sources: int) -> SearchResponse: ...


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


class OpenAIWebSearchProvider:
    """Read-only web research through the OpenAI Responses API web_search tool."""

    def __init__(self, model: str):
        self.model = model

    def search(self, query: str, max_sources: int) -> SearchResponse:
        from openai import OpenAI  # type: ignore[import-not-found]

        client = OpenAI()
        response = client.responses.create(
            model=self.model,
            tools=[{"type": "web_search"}],
            include=["web_search_call.action.sources"],
            input=(
                "Perform read-only web research for a safety-first business agent with a simulated "
                "$100 budget. Search and follow relevant sources as needed. Do not submit forms, "
                "log in, download programs, contact anyone, or take any external action. Distinguish "
                "source-supported findings from assumptions. Prefer primary/current sources. "
                f"Research task: {query}"
            ),
            max_output_tokens=1800,
        )
        payload = response.model_dump(mode="json")
        sources: list[WebSource] = []
        seen: set[str] = set()
        for item in _walk(payload):
            url = item.get("url")
            if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                continue
            if url in seen:
                continue
            title = item.get("title")
            sources.append(
                WebSource(url=url, title=title if isinstance(title, str) else url)
            )
            seen.add(url)
            if len(sources) >= max_sources:
                break
        return SearchResponse(findings=response.output_text.strip(), sources=sources)


class ResearchService:
    def __init__(
        self, database: Database, provider: WebSearchProvider, limits: ResearchLimits
    ):
        self.database = database
        self.provider = provider
        self.limits = limits

    @staticmethod
    def _fingerprint(query: str, url: str, opportunity: str) -> str:
        normalized = "\n".join(
            (query.strip().lower(), url.strip().lower(), opportunity.lower())
        )
        return hashlib.sha256(normalized.encode()).hexdigest()

    def _fresh_records(self, query: str) -> list[dict]:
        cutoff = datetime.now(UTC) - self.limits.stale_after
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM research WHERE query=? ORDER BY id", (query,)
            ).fetchall()
        records = [dict(row) for row in rows]
        return [
            item
            for item in records
            if datetime.fromisoformat(item["retrieved_at"]) >= cutoff
        ]

    def _save(self, query: str, response: SearchResponse, remaining: int) -> list[dict]:
        saved: list[dict] = []
        seen: set[str] = set()
        retrieved_at = utc_now()
        for source in response.sources[:remaining]:
            opportunity = "broad opportunity discovery"
            fingerprint = self._fingerprint(query, source.url, opportunity)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            with self.database.connect() as connection:
                connection.execute(
                    "INSERT INTO research(query, source_url, source_title, retrieved_at, "
                    "findings, opportunity, confidence, evidence_status, fingerprint) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'medium', 'inferred', ?) "
                    "ON CONFLICT(fingerprint) DO UPDATE SET source_title=excluded.source_title, "
                    "retrieved_at=excluded.retrieved_at, findings=excluded.findings, "
                    "confidence=excluded.confidence, evidence_status=excluded.evidence_status",
                    (
                        query,
                        source.url,
                        source.title,
                        retrieved_at,
                        response.findings,
                        opportunity,
                        fingerprint,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM research WHERE fingerprint=?", (fingerprint,)
                ).fetchone()
                if row is None:  # pragma: no cover - guarded by the preceding upsert
                    raise RuntimeError("research record was not persisted")
                saved.append(dict(row))
        return saved

    def collect(self, queries: tuple[str, ...] = DISCOVERY_QUERIES) -> ResearchReport:
        self.database.initialize()
        started_at = utc_now()
        with self.database.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO research_runs(started_at, status) VALUES (?, 'running')",
                (started_at,),
            )
            run_id = cursor.lastrowid
            if run_id is None:  # pragma: no cover - SQLite always supplies this
                raise RuntimeError("SQLite did not return a research run ID")

        records: list[dict] = []
        errors: list[str] = []
        api_calls = 0
        cache_hits = 0
        sources_saved = 0
        for query in queries[: self.limits.max_queries]:
            if len(records) >= self.limits.max_sources:
                break
            fresh = self._fresh_records(query)
            if fresh:
                cache_hits += 1
                records.extend(fresh[: self.limits.max_sources - len(records)])
                continue
            try:
                api_calls += 1
                remaining = self.limits.max_sources - len(records)
                response = self.provider.search(query, remaining)
                if not response.sources:
                    errors.append(
                        f"No attributable sources returned for query: {query}"
                    )
                    continue
                saved = self._save(query, response, remaining)
                sources_saved += len(saved)
                records.extend(saved)
            except (
                Exception
            ) as exc:  # provider/network failures must not destroy saved state
                errors.append(
                    f"Research failed for query {query!r}: {type(exc).__name__}: {exc}"
                )

        status = "completed" if not errors else ("partial" if records else "failed")
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE research_runs SET completed_at=?, api_calls=?, sources_saved=?, "
                "cache_hits=?, errors=?, status=? WHERE id=?",
                (
                    utc_now(),
                    api_calls,
                    sources_saved,
                    cache_hits,
                    len(errors),
                    status,
                    run_id,
                ),
            )
        return ResearchReport(records, api_calls, cache_hits, errors)


def recent_research(database: Database, limit: int = 50) -> list[dict]:
    with database.connect() as connection:
        rows = connection.execute(
            "SELECT * FROM research ORDER BY retrieved_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
