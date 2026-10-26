"""Local news and development claims for a saved parcel.

News is discovery evidence: it can surface a reported flood, dispute or project, or corroborate a claim. It never
verifies title, proves the absence of a dispute, or certifies flood safety, and it never changes the decision.

Providers sit behind a small interface so another source (an RSS feed, an official notification index) can be added.
The only provider today is GDELT DOC 2.0 (free, no key; headline-level metadata, roughly one request per 5 seconds).
Results are cached per parcel for 24 hours and always carry their retrieval time; a failed search is reported as
unavailable, never as "no news".
"""

from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

NEWS_TTL = timedelta(hours=24)
# Whole search, all topics: past this the buyer sees "temporarily unavailable" instead of waiting minutes
# (measured 2026-10-26: 189 s of rate-limit back-offs before a 429 was reported).
SEARCH_BUDGET_S = 45.0
# GDELT DOC 2.0 searches back to 2017-01-01 (its blog posts disagree; verified 2026-10-26 by a 2018 Coimbatore query).
ARCHIVE_START = datetime(2017, 1, 1, tzinfo=timezone.utc)
SEARCH_YEARS = 10
MAX_RECORDS = 250  # GDELT's ceiling per query
STALE_AFTER_DAYS = 730
TOPICS = {
    "hazards": ("Flooding, waterlogging or road closures",
                ["flood", "flooded", "waterlogging", "waterlogged", "inundated", "inundation", "\"road closed\"", "submerged"]),
    "legal_planning": ("Disputes, encroachment, demolition or planning changes",
                       ["dispute", "encroachment", "demolition", "demolished", "\"land grab\"", "\"land acquisition\"",
                        "\"master plan\"", "unapproved", "\"layout approval\"", "rera"]),
    "development": ("Roads, transport, industry, layouts, schools or hospitals",
                    ["highway", "\"ring road\"", "bypass", "metro", "railway", "industrial", "sipcot", "\"it park\"",
                     "layout", "township", "school", "hospital", "college"]),
}
# Project status as the headline words it, first match wins. A headline is not a sanction order: it is shown as "reported".
PROJECT_STATUS = [
    ("cancelled", re.compile(r"\b(scrapped|cancel+ed|cancels|dropped|shelved|withdrawn|abandoned)\b", re.I)),
    ("completed", re.compile(r"\b(inaugurat\w*|opened|thrown open|completed|commissioned)\b", re.I)),
    ("under_construction", re.compile(r"\b(under construction|foundation stone|works? (begins?|began|started|in progress)|construction (begins|began|starts|started|under ?way))\b", re.I)),
    ("approved", re.compile(r"\b(approved|sanction(ed)?|nod|go-ahead|cleared|notified|funds? released)\b", re.I)),
    ("proposed", re.compile(r"\b(proposed|proposal|plans?|planned|mooted|to come up|dpr|feasibility|survey)\b", re.I)),
]
SPECULATIVE = re.compile(r"\b(proposed|propose|plan|plans|planned|likely|may|soon|to come up|mooted|expected|demand|sought)\b", re.I)


class NewsUnavailable(RuntimeError):
    """The provider could not be searched; this is not the same as finding nothing."""


class NewsProvider(Protocol):
    name: str
    coverage: str

    def search(self, query: str, since: datetime, deadline: float | None = None) -> list[dict[str, Any]]: ...


class GdeltProvider:
    name = "GDELT DOC 2.0 (gdeltproject.org)"
    coverage = ("Online news worldwide indexed by GDELT since 2017, including Indian English, Tamil and Telugu outlets. "
                "Headlines and links only; GDELT matches the query against article text it has indexed. It is not every "
                "news site, and paywalled or unindexed articles are missing.")
    url = "https://api.gdeltproject.org/api/v2/doc/doc"
    _lock = threading.Lock()
    _last = 0.0
    MIN_INTERVAL_S = 6.0  # GDELT asks for at most one request every 5 seconds
    BACKOFF_429_S = 15.0  # after a 429 it keeps refusing for a while; one longer pause, then report unavailable
    COOLDOWN_429_S = 120.0  # after reporting a 429, send no request until this passes
    _cooldown_until = 0.0

    def _rate_limited(self) -> NewsUnavailable:
        GdeltProvider._cooldown_until = time.monotonic() + self.COOLDOWN_429_S
        return NewsUnavailable("GDELT is rate-limiting requests (HTTP 429); try again in a few minutes")

    def search(self, query: str, since: datetime, deadline: float | None = None) -> list[dict[str, Any]]:
        def left() -> float:
            return float("inf") if deadline is None else deadline - time.monotonic()

        wait_left = GdeltProvider._cooldown_until - time.monotonic()
        if wait_left > 0:  # GDELT refused us moments ago: asking again only prolongs the block
            raise NewsUnavailable(f"GDELT is rate-limiting requests (HTTP 429); TerraScope waits {wait_left:.0f} s before asking again")
        params = {"query": query, "mode": "artlist", "format": "json", "maxrecords": MAX_RECORDS, "sort": "datedesc",
                  "startdatetime": since.strftime("%Y%m%d%H%M%S")}
        for attempt in range(2):
            with GdeltProvider._lock:  # bounded: one request in flight, spaced out, across all parcels
                wait = GdeltProvider._last + self.MIN_INTERVAL_S - time.monotonic()
                if wait > 0:
                    if wait > left() - 5:
                        raise NewsUnavailable("the news search ran out of time (provider rate limit)")
                    time.sleep(wait)
                budget = min(25.0, left())
                if budget < 5:
                    raise NewsUnavailable("the news search ran out of time")
                try:
                    # GDELT's TLS handshake can take over 5 s from India; a timeout is retried once, then reported.
                    response = httpx.get(self.url, params=params, timeout=httpx.Timeout(budget, connect=min(12.0, budget)))
                except httpx.HTTPError as error:
                    if attempt == 0:
                        continue
                    raise NewsUnavailable(f"GDELT could not be reached: {error}") from error
                finally:
                    GdeltProvider._last = time.monotonic()
            text = response.text.strip()
            if response.status_code == 200 and text.startswith("{"):
                return json.loads(text).get("articles") or []
            if response.status_code == 200 and not text:
                return []
            if (response.status_code == 429 or "limit requests" in text.lower()) and attempt == 0:
                if self.BACKOFF_429_S > left() - 10:
                    raise self._rate_limited()
                time.sleep(self.BACKOFF_429_S)
                continue
            if response.status_code == 429 or "limit requests" in text.lower():
                raise self._rate_limited()
            raise NewsUnavailable(f"GDELT returned HTTP {response.status_code}: {text[:160]}")
        raise self._rate_limited()


def _ascii(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().strip()


def spelling_variants(name: str) -> list[str]:
    """Common transliteration variants of an Indian place name (Senjeri / Senjery, Tiruvannamalai / Thiruvannamalai)."""
    name = _ascii(name)
    if len(name) < 4 or " " in name:  # landmarks and multi-word names are searched as written
        return [name] if name else []
    variants = {name}
    swaps = [("ee", "i"), ("i", "ee"), ("oo", "u"), ("th", "t"), ("t", "th"), ("v", "w"), ("w", "v")]
    for old, new in swaps:
        position = name.lower().find(old, 1)  # never the first letter, so the capital is kept
        if position > 0:
            variants.add(name[:position] + new + name[position + len(old):])
    if name.startswith("Th"):  # Thiruvannamalai / Tiruvannamalai
        variants.add("T" + name[2:])
    elif name.startswith("T"):
        variants.add("Th" + name[1:])
    if name.lower().endswith("i"):
        variants.add(name[:-1] + "y")
    if name.lower().endswith("y"):
        variants.add(name[:-1] + "i")
    return sorted(variants, key=lambda v: (v != name, v))[:5]


def place_terms(snapshot: dict[str, Any]) -> dict[str, Any]:
    """The locality (with variants) and the district that every result must mention."""
    location = snapshot.get("location") or {}
    address = location.get("address") or ""
    parts = [p.strip() for p in address.split(",") if p.strip()]
    locality = location.get("village") or next((re.sub(r"\s*\(PIN.*\)", "", p) for p in parts
                                                 if not re.match(r"^\d", p) and len(p) > 3), None)
    district = location.get("district") or (parts[-3] if len(parts) >= 3 else None)
    if district and locality and _ascii(district).lower() == _ascii(locality).lower():
        district = location.get("state")
    return {"locality": locality, "variants": spelling_variants(locality) if locality else [],
            "district": _ascii(district) if district else None, "state": location.get("state")}


def _norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9஀-௿ఀ-౿]+", " ", (title or "").lower()).strip()[:80]


def _seen(article: dict[str, Any]) -> datetime | None:
    try:
        return datetime.strptime(article.get("seendate", ""), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def project_status(topic: str, title: str) -> str | None:
    if topic == "hazards":
        return None
    return next((status for status, pattern in PROJECT_STATUS if pattern.search(title or "")), "unknown")


def classify(articles_by_topic: dict[str, list[dict[str, Any]]], now: datetime,
             variants: list[str] | None = None) -> list[dict[str, Any]]:
    """Group duplicates and syndicated copies, then label each event: official, corroborated or single report.
    Newest year first; within a year, official and corroborated items first."""
    names = [_norm_title(v) for v in variants or []]
    groups: dict[str, dict[str, Any]] = {}
    for topic, articles in articles_by_topic.items():
        for article in articles:
            key = _norm_title(article.get("title", ""))
            if not key:
                continue
            domain = (article.get("domain") or urlparse(article.get("url", "")).netloc).lower()
            group = groups.setdefault(key, {"title": article.get("title"), "topic": topic, "articles": [], "domains": set()})
            if domain not in group["domains"]:
                group["domains"].add(domain)
                group["articles"].append({"url": article.get("url"), "publisher": domain, "seen": _seen(article),
                                          "language": article.get("language")})
    items = []
    for group in groups.values():
        dates = [a["seen"] for a in group["articles"] if a["seen"]]
        first = min(dates) if dates else None
        official = any(d.endswith((".gov.in", ".nic.in")) for d in group["domains"])
        status = ("official_source" if official else
                  "corroborated" if len(group["domains"]) >= 2 else "single_report")
        lead = sorted(group["articles"], key=lambda a: a["seen"] or now)[0]
        items.append({
            "title": group["title"],
            "topic": group["topic"],
            "topic_label": TOPICS[group["topic"]][0],
            "publisher": lead["publisher"],
            "url": lead["url"],
            "published": first.date().isoformat() if first else None,
            "language": lead["language"],
            "outlets": len(group["domains"]),
            "other_urls": [a["url"] for a in group["articles"] if a is not lead][:4],
            "verification": status,
            "evidence_type": "official_publication" if official else "news_report",
            # GDELT matched the article text; when the headline itself does not name the place, the item may be about
            # somewhere else that merely mentions it.
            "locality_in_headline": any(n and n in _norm_title(group["title"] or "") for n in names),
            "project_status": project_status(group["topic"], group["title"]),
            "speculative": bool(SPECULATIVE.search(group["title"] or "")),
            "stale": bool(first and (now - first).days > STALE_AFTER_DAYS),
        })
    order = {"official_source": 0, "corroborated": 1, "single_report": 2}
    items.sort(key=lambda i: i["published"] or "", reverse=True)
    return sorted(items, key=lambda i: (-int((i["published"] or "0")[:4]), order[i["verification"]]))


def search_area_news(snapshot: dict[str, Any], provider: NewsProvider, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    terms = place_terms(snapshot)
    since = max(ARCHIVE_START, now - timedelta(days=365 * SEARCH_YEARS))
    base = {"provider": provider.name, "coverage": provider.coverage, "retrieved_at": now.isoformat(timespec="seconds"),
            "searched_from": since.date().isoformat(), "place": terms,
            "limitations": ("News can surface a reported problem or project; it cannot verify title, prove that no dispute "
                            "exists, or show that a plot is flood-safe. Finding nothing means nothing was indexed for these "
                            "words, not that nothing happened. Conflicting reports cannot be detected from headlines. "
                            "Dates are when GDELT saw the article, not when the event happened; project status is the "
                            "headline's wording, not a sanction record; distance from the plot is not known.")}
    if not terms["variants"] or not terms["district"]:
        return {**base, "status": "not_searched", "queries": [], "items": [],
                "reason": "The report has no locality and district name to search for."}
    names = " OR ".join(f'"{v}"' for v in terms["variants"])
    queries, by_topic = [], {}
    deadline = time.monotonic() + SEARCH_BUDGET_S
    try:
        for topic, (_, words) in TOPICS.items():
            query = f'({names}) "{terms["district"]}" ({" OR ".join(words)}) sourcecountry:IN'
            queries.append({"topic": topic, "query": query})
            by_topic[topic] = provider.search(query, since, deadline=deadline)
    except NewsUnavailable as error:
        return {**base, "status": "unavailable", "queries": queries, "items": [], "reason": str(error)}
    items = classify(by_topic, now, terms["variants"])
    return {**base, "status": "results" if items else "no_results", "queries": queries, "items": items,
            "raw_articles": sum(len(v) for v in by_topic.values()),
            # A topic at the record ceiling has older articles that GDELT did not return.
            "truncated_topics": [t for t, v in by_topic.items() if len(v) >= MAX_RECORDS]}


# --- development claims ---------------------------------------------------------------------------------------

PROJECT_EFFECT = {
    "road": "If built, it could shorten travel to the plot; it is not assumed to be built.",
    "transport": "If built, it could improve public transport access; it is not assumed to be built.",
    "industrial": "If built, it could add jobs but also traffic, noise or pollution nearby; it is not assumed to be built.",
    "residential_layout": "If developed, it would add housing and activity nearby; approval and completion are not assumed.",
    "school": "If opened, it would bring a school closer; it is not assumed to open.",
    "hospital": "If opened, it would bring healthcare closer; it is not assumed to open.",
    "commercial": "If built, it could bring shops and services closer; it is not assumed to be built.",
    "other": "Its effect depends on what is built and whether it is completed.",
}


def claim_status(evidence_url: str | None) -> str:
    """User claims stay unverified. An official link is noted, but TerraScope does not read or verify it."""
    if not evidence_url:
        return "user_provided"
    host = urlparse(evidence_url).netloc.lower()
    return "official_link_provided" if host.endswith((".gov.in", ".nic.in")) else "link_provided"


# --- API ---------------------------------------------------------------------------------------------------------

import hashlib  # noqa: E402
from typing import Literal  # noqa: E402

from fastapi import APIRouter, HTTPException  # noqa: E402
from pydantic import BaseModel, Field, HttpUrl  # noqa: E402

from routers.store import delete_claim, get_cached_news, get_latest_for_parcel, list_claims, put_cached_news, save_claim  # noqa: E402

router = APIRouter()
PROVIDER: NewsProvider = GdeltProvider()
NEWS_CACHE_VERSION = "news-2"
_key_locks: dict[str, threading.Lock] = {}


def _snapshot(parcel_id: str) -> dict[str, Any]:
    latest = get_latest_for_parcel(parcel_id)
    if latest is None:
        raise HTTPException(status_code=404, detail=f"Parcel not found: {parcel_id}")
    return latest[1]


@router.get("/api/v1/parcels/{parcel_id}/area-news")
def area_news(parcel_id: str, refresh: bool = False) -> dict[str, Any]:
    """Local news for the parcel's locality. Cached 24 h per locality and provider; never shown as permanently current."""
    snapshot = _snapshot(parcel_id)
    terms = place_terms(snapshot)
    key = hashlib.sha256(json.dumps([NEWS_CACHE_VERSION, PROVIDER.name, terms["variants"], terms["district"]]).encode()).hexdigest()
    with _key_locks.setdefault(key, threading.Lock()):  # concurrent requests for one locality search once
        if not refresh:
            cached = get_cached_news(key, NEWS_TTL.total_seconds())
            if cached is not None:
                return {**cached, "cached": True}
        result = search_area_news(snapshot, PROVIDER)
        if result["status"] in ("results", "no_results"):  # a failed search is never cached
            put_cached_news(key, result)
    return {**result, "cached": False, "cache_age_s": 0}


class DevelopmentClaim(BaseModel):
    claim: str = Field(min_length=5, max_length=500)
    project_type: Literal["road", "transport", "industrial", "residential_layout", "school", "hospital", "commercial", "other"]
    location_text: str | None = Field(None, max_length=200)
    distance_m: float | None = Field(None, ge=0, le=100_000)
    expected_date: str | None = Field(None, max_length=40)
    source: Literal["resident", "broker", "seller", "news", "official", "other"]
    evidence_url: HttpUrl | None = None
    checked_on: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")


@router.get("/api/v1/parcels/{parcel_id}/claims")
def read_claims(parcel_id: str) -> dict[str, Any]:
    _snapshot(parcel_id)
    return {"claims": [{**c, "effect": PROJECT_EFFECT[c["project_type"]]} for c in list_claims(parcel_id)]}


@router.post("/api/v1/parcels/{parcel_id}/claims")
def add_claim(parcel_id: str, claim: DevelopmentClaim) -> dict[str, Any]:
    _snapshot(parcel_id)
    data = claim.model_dump(mode="json")
    data["verification"] = claim_status(data.get("evidence_url"))
    claim_id = save_claim(parcel_id, data)
    return {"id": claim_id, **data, "effect": PROJECT_EFFECT[data["project_type"]]}


@router.delete("/api/v1/parcels/{parcel_id}/claims/{claim_id}")
def remove_claim(parcel_id: str, claim_id: int) -> dict[str, Any]:
    if not delete_claim(parcel_id, claim_id):
        raise HTTPException(status_code=404, detail="Claim not found for this parcel.")
    return {"deleted": claim_id}
