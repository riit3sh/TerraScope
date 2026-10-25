"""Local news and development claims: behaviour with a fake provider (no network), on a temporary store."""

import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from routers import area_intel, store  # noqa: E402

NOW = datetime(2026, 10, 25, tzinfo=timezone.utc)
SNAPSHOT = {"parcel_id": "p1", "metadata": {"analysis_snapshot_id": "s1"},
            "location": {"address": "Senjeri (PIN 641669), Coimbatore, Tamil Nadu, India", "district": None, "state": "Tamil Nadu"}}


def art(title, domain, days_ago=10):
    return {"title": title, "domain": domain, "url": f"https://{domain}/{abs(hash(title)) % 10**6}",
            "seendate": (NOW - timedelta(days=days_ago)).strftime("%Y%m%dT%H%M%SZ"), "language": "English"}


class Fake:
    name, coverage = "fake", "test"

    def __init__(self, by_topic=None, fail=False):
        self.by_topic, self.fail, self.calls = by_topic or {}, fail, []

    def search(self, query, since, deadline=None):
        self.calls.append(query)
        if self.fail:
            raise area_intel.NewsUnavailable("provider down")
        topic = next(t for t, (_, words) in area_intel.TOPICS.items() if words[0] in query)
        return self.by_topic.get(topic, [])


def test_place_terms_use_the_locality_its_spellings_and_the_district() -> None:
    terms = area_intel.place_terms(SNAPSHOT)
    assert terms["locality"] == "Senjeri" and "Senjery" in terms["variants"] and terms["district"] == "Coimbatore"


def test_every_query_requires_the_locality_and_the_district() -> None:
    fake = Fake()
    area_intel.search_area_news(SNAPSHOT, fake, NOW)
    assert len(fake.calls) == 3 and all('"Senjeri"' in q and '"Coimbatore"' in q for q in fake.calls)


def test_no_results_is_reported_as_no_results_with_what_was_searched() -> None:
    result = area_intel.search_area_news(SNAPSHOT, Fake(), NOW)
    assert result["status"] == "no_results" and result["items"] == []
    assert len(result["queries"]) == 3 and result["searched_from"] == "2023-10-26"
    assert "not that nothing happened" in result["limitations"]


def test_a_corroborated_adverse_event_is_distinguished_from_a_single_report() -> None:
    flood = "Senjeri village roads flooded after heavy rain"
    result = area_intel.search_area_news(SNAPSHOT, Fake({"hazards": [art(flood, "thehindu.com"), art(flood, "dtnext.in"),
                                                                     art("Dispute over Senjeri temple land", "localpaper.in")]}), NOW)
    flood_item = next(i for i in result["items"] if i["title"] == flood)
    assert flood_item["verification"] == "corroborated" and flood_item["outlets"] == 2, "syndicated copies merged"
    single = next(i for i in result["items"] if i["title"].startswith("Dispute"))
    assert single["verification"] == "single_report"
    assert sum(1 for i in result["items"] if i["title"] == flood) == 1, "no duplicate events"


def test_official_sources_rank_first_and_stale_or_speculative_reports_are_labelled() -> None:
    items = area_intel.search_area_news(SNAPSHOT, Fake({"development": [
        art("Ring road proposed near Senjeri, Coimbatore", "news.example.in", days_ago=900),
        art("Senjeri layout approval notified", "tnhb.tn.gov.in", days_ago=5)]}), NOW)["items"]
    assert items[0]["verification"] == "official_source"
    old = next(i for i in items if i["title"].startswith("Ring road"))
    assert old["speculative"] and old["stale"]


def test_a_provider_failure_is_unavailable_never_no_news() -> None:
    result = area_intel.search_area_news(SNAPSHOT, Fake(fail=True), NOW)
    assert result["status"] == "unavailable" and "provider down" in result["reason"]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKEND_STORE_PATH", str(tmp_path / "isolated.sqlite3"))
    store.init_store()
    store.save_snapshot(SNAPSHOT)
    from terrascope_backend_api.main import app
    return TestClient(app)


def test_news_is_cached_for_a_day_and_failures_are_not_cached(client, monkeypatch) -> None:
    fake = Fake({"hazards": [art("Senjeri flooded", "thehindu.com")]})
    monkeypatch.setattr(area_intel, "PROVIDER", fake)
    first = client.get("/api/v1/parcels/p1/area-news").json()
    second = client.get("/api/v1/parcels/p1/area-news").json()
    assert first["cached"] is False and second["cached"] is True and len(fake.calls) == 3
    assert second["retrieved_at"] == first["retrieved_at"], "a cached result keeps its real retrieval time"
    client.get("/api/v1/parcels/p1/area-news?refresh=true")
    assert len(fake.calls) == 6
    down = Fake(fail=True)
    monkeypatch.setattr(area_intel, "PROVIDER", down)
    assert client.get("/api/v1/parcels/p1/area-news?refresh=true").json()["status"] == "unavailable"
    monkeypatch.setattr(area_intel, "PROVIDER", fake)
    assert client.get("/api/v1/parcels/p1/area-news").json()["status"] == "results", "the failure was not cached"
    assert client.get("/api/v1/parcels/missing/area-news").status_code == 404


def test_expired_news_is_searched_again(client, monkeypatch) -> None:
    fake = Fake()
    monkeypatch.setattr(area_intel, "PROVIDER", fake)
    client.get("/api/v1/parcels/p1/area-news")
    monkeypatch.setattr(area_intel, "NEWS_TTL", timedelta(seconds=0))
    client.get("/api/v1/parcels/p1/area-news")
    assert len(fake.calls) == 6


def test_claims_stay_user_provided_and_are_validated(client) -> None:
    ok = client.post("/api/v1/parcels/p1/claims", json={
        "claim": "A resident says a ring road will pass 1 km north", "project_type": "road", "source": "resident",
        "distance_m": 1000, "checked_on": "2026-10-25"}).json()
    assert ok["verification"] == "user_provided" and "not assumed to be built" in ok["effect"]
    official = client.post("/api/v1/parcels/p1/claims", json={
        "claim": "Layout approval notified", "project_type": "residential_layout", "source": "official",
        "evidence_url": "https://www.tn.gov.in/notice/123"}).json()
    assert official["verification"] == "official_link_provided"
    assert client.post("/api/v1/parcels/p1/claims", json={"claim": "x", "project_type": "road", "source": "resident"}).status_code == 422
    assert client.post("/api/v1/parcels/p1/claims", json={"claim": "valid claim", "project_type": "airport", "source": "resident"}).status_code == 422
    assert len(client.get("/api/v1/parcels/p1/claims").json()["claims"]) == 2
    assert client.delete(f"/api/v1/parcels/p1/claims/{ok['id']}").status_code == 200
    assert client.delete(f"/api/v1/parcels/p1/claims/{ok['id']}").status_code == 404


def test_report_list_marks_evaluations_without_parsing_them(client) -> None:
    store.save_evaluation("p1", "s1", {"verdict": {"recommendation": "WAIT"}})
    store.save_snapshot({"parcel_id": "p2", "metadata": {"analysis_snapshot_id": "s2"}, "location": {"address": "X"}})
    reports = {r["parcel_id"]: r for r in client.get("/api/v1/parcels").json()["reports"]}
    assert reports["p1"]["has_evaluation"] is True and reports["p2"]["has_evaluation"] is False
    assert reports["p1"]["address"].startswith("Senjeri")


def test_concurrent_searches_are_spaced_by_the_provider_limit(monkeypatch) -> None:
    calls = []

    class Clock(area_intel.GdeltProvider):
        MIN_INTERVAL_S = 0.2

    def fake_get(url, params, timeout):
        calls.append(time.monotonic())
        return type("R", (), {"status_code": 200, "text": '{"articles": []}'})()

    monkeypatch.setattr(area_intel.httpx, "get", fake_get)
    provider = Clock()
    threads = [threading.Thread(target=provider.search, args=("q", NOW)) for _ in range(3)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    gaps = [b - a for a, b in zip(calls, calls[1:])]
    # Windows sleeps can wake one clock tick (~16 ms) early; the real 5.5 s spacing has 0.5 s of margin over 5 s.
    assert len(calls) == 3 and all(g >= 0.17 for g in gaps), gaps


def test_concurrent_requests_for_one_locality_search_once(client, monkeypatch) -> None:
    """React's development mode, two tabs or a double click must not double the provider requests."""
    fake = Fake({"hazards": [art("Senjeri flooded", "thehindu.com")]})
    slow_search = fake.search

    def slow(query, since, deadline=None):
        time.sleep(0.05)
        return slow_search(query, since)

    fake.search = slow
    monkeypatch.setattr(area_intel, "PROVIDER", fake)
    results = []
    threads = [threading.Thread(target=lambda: results.append(client.get("/api/v1/parcels/p1/area-news").json()))
               for _ in range(3)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(fake.calls) == 3, "one search (3 topic queries), not three"
    assert sorted(r["cached"] for r in results) == [False, True, True]


def test_a_rate_limited_provider_gives_up_within_the_search_budget(monkeypatch) -> None:
    """Regression (2026-10-26): repeated HTTP 429 back-offs kept the buyer waiting 189 s before "unavailable"."""
    def always_429(url, params, timeout):
        return type("R", (), {"status_code": 429, "text": "Please limit requests to one every 5 seconds"})()

    class Quick(area_intel.GdeltProvider):
        MIN_INTERVAL_S, BACKOFF_429_S = 0.01, 0.5

    monkeypatch.setattr(area_intel.httpx, "get", always_429)
    monkeypatch.setattr(area_intel, "SEARCH_BUDGET_S", 12.0)
    began = time.monotonic()
    result = area_intel.search_area_news(SNAPSHOT, Quick(), NOW)
    assert result["status"] == "unavailable" and "429" in result["reason"]
    assert time.monotonic() - began < 12.0, "the whole search stays within its budget"
