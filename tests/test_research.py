import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from money_agent.research import (
    OpenAIWebSearchProvider,
    ResearchLimits,
    ResearchService,
    SearchResponse,
    WebSource,
)
from money_agent.ledger import Ledger
from money_agent.storage import Database


class FakeProvider:
    def __init__(self, responses=None, error=None):
        self.responses = list(responses or [])
        self.error = error
        self.calls = []

    def search(self, query, max_sources):
        self.calls.append((query, max_sources))
        if self.error:
            raise self.error
        return (
            self.responses.pop(0)
            if self.responses
            else SearchResponse("Nothing found", [])
        )


def response(url="https://example.com/report", title="Primary report"):
    return SearchResponse(
        findings="The source reports current customer demand; margin remains an inference.",
        sources=[WebSource(url, title)],
    )


def service(tmp_path, provider, **limits):
    database = Database(tmp_path / "agent.db")
    database.initialize()
    return database, ResearchService(database, provider, ResearchLimits(**limits))


def test_research_persists_source_attribution(tmp_path):
    database, research = service(tmp_path, FakeProvider([response()]))
    report = research.collect(("customer demand",))
    assert report.records[0]["query"] == "customer demand"
    assert report.records[0]["source_url"] == "https://example.com/report"
    assert report.records[0]["source_title"] == "Primary report"
    assert report.records[0]["evidence_status"] == "inferred"
    assert report.records[0]["retrieved_at"]
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM research").fetchone()[0] == 1
    summary = Ledger(database).summary()
    assert summary.current_cash_cents == 10_000
    assert summary.realized_profit_cents == 0


def test_fresh_research_is_reused_without_api_call(tmp_path):
    provider = FakeProvider([response()])
    _, research = service(tmp_path, provider)
    research.collect(("pricing",))
    second = research.collect(("pricing",))
    assert len(provider.calls) == 1
    assert second.cache_hits == 1
    assert second.api_calls == 0


def test_stale_research_is_refreshed_without_duplicate(tmp_path):
    provider = FakeProvider([response(), response(title="Updated title")])
    database, research = service(tmp_path, provider, stale_after=timedelta(hours=1))
    first = research.collect(("pricing",))
    old = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    with database.connect() as connection:
        connection.execute("UPDATE research SET retrieved_at=?", (old,))
    second = research.collect(("pricing",))
    assert len(provider.calls) == 2
    assert second.records[0]["id"] == first.records[0]["id"]
    assert second.records[0]["source_title"] == "Updated title"
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM research").fetchone()[0] == 1


def test_query_and_source_limits_are_enforced(tmp_path):
    many_sources = SearchResponse(
        "Evidence",
        [
            WebSource(f"https://example.com/{number}", f"Source {number}")
            for number in range(5)
        ],
    )
    provider = FakeProvider([many_sources, many_sources])
    _, research = service(tmp_path, provider, max_queries=1, max_sources=2)
    report = research.collect(("one", "two"))
    assert len(provider.calls) == 1
    assert len(report.records) == 2
    assert provider.calls[0][1] == 2


def test_failure_is_recorded_and_does_not_raise(tmp_path):
    database, research = service(
        tmp_path, FakeProvider(error=TimeoutError("network down"))
    )
    report = research.collect(("demand",))
    assert report.records == []
    assert report.api_calls == 1
    assert "TimeoutError" in report.errors[0]
    with database.connect() as connection:
        run = connection.execute("SELECT status, errors FROM research_runs").fetchone()
    assert tuple(run) == ("failed", 1)


def test_empty_results_are_not_treated_as_research(tmp_path):
    _, research = service(
        tmp_path, FakeProvider([SearchResponse("Unsupported text", [])])
    )
    report = research.collect(("demand",))
    assert report.records == []
    assert "No attributable sources" in report.errors[0]


def test_duplicate_sources_are_stored_once(tmp_path):
    duplicate = SearchResponse(
        "Evidence",
        [
            WebSource("https://example.com/a", "A"),
            WebSource("https://example.com/a", "A duplicate"),
        ],
    )
    database, research = service(tmp_path, FakeProvider([duplicate]))
    report = research.collect(("demand",))
    assert len(report.records) == 1
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM research").fetchone()[0] == 1


def test_openai_provider_exposes_only_read_only_web_search(monkeypatch):
    captured = {}

    class Responses:
        def create(self, **kwargs):
            captured.update(kwargs)
            payload = {
                "output": [
                    {
                        "action": {
                            "sources": [
                                {"url": "https://example.com", "title": "Example"}
                            ]
                        }
                    }
                ]
            }
            return SimpleNamespace(
                output_text="Attributed finding",
                model_dump=lambda **_: payload,
            )

    fake_module = SimpleNamespace(OpenAI=lambda: SimpleNamespace(responses=Responses()))
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    result = OpenAIWebSearchProvider("test-model").search("pricing", 3)
    assert captured["tools"] == [{"type": "web_search"}]
    assert "Do not submit forms" in captured["input"]
    assert result.sources == [WebSource("https://example.com", "Example")]
