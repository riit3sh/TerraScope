"""AI explanation guards: unassessed checks never read as clear, whole sentences, place names, honest citations."""

from __future__ import annotations

import json

import pytest

import land_analyst

SNAPSHOT = {
    "location": {"address": "Lancor Infinys, Medavakkam Main Rd, Keelkattalai, Tamil Nadu 600117, India"},
    "evidence": [
        {"source_reference": "OpenStreetMap, Geofabrik extract", "source_type": "openstreetmap",
         "title": "Nearby infrastructure", "summary": "Accessibility 94/100: nearest mapped road 17 m, school 410 m."},
        {"source_reference": "JRC global river flood hazard maps v2.1.2", "source_type": "jrc_flood_hazard",
         "title": "Modelled river flooding by return period",
         "summary": "River flood hazard not assessed: the JRC hazard-map server did not respond."},
        {"source_reference": "Sentinel-2 L2A (Microsoft Planetary Computer)", "source_type": "satellite",
         "title": "Land-cover change (NDVI/NDBI) from observed imagery", "summary": "6 cloud-screened observations."},
    ],
}


def _answer(monkeypatch, payload):
    monkeypatch.setenv("DEEPINFRA_API_KEY", "di-test")
    sent = {}

    def fake(provider, request, max_wait=0):
        sent["prompt"] = request["messages"][0]["content"]
        return payload

    monkeypatch.setattr(land_analyst, "_groq_json", fake)
    return land_analyst.generate_evaluation_explanation(SNAPSHOT), sent


def test_prompt_names_the_place_and_lists_unassessed_checks(monkeypatch):
    _, sent = _answer(monkeypatch, {"answer_text": "Lancor Infinys has good road access.", "citations": [
        {"claim": "Lancor Infinys has good road access to a mapped road.", "source_reference": "OpenStreetMap, Geofabrik extract"}]})
    facts = json.loads(sent["prompt"].split("FACTS:\n", 1)[1])
    assert facts["place"] == "Lancor Infinys"
    assert facts["not_assessed"] == ["Modelled river flooding by return period"]


def test_unassessed_river_flooding_described_as_clear_is_rejected(monkeypatch):
    with pytest.raises(RuntimeError, match="unassessed"):
        _answer(monkeypatch, {"answer_text": "No river flood hazard was found for the plot.", "citations": [
            {"claim": "Nearest mapped road 17 m.", "source_reference": "OpenStreetMap, Geofabrik extract"}]})


def test_unrelated_and_factor_name_citations_are_dropped_not_shown(monkeypatch):
    result, _ = _answer(monkeypatch, {"answer_text": "Road access is good. Legal records are unavailable.", "citations": [
        {"claim": "Nearest mapped road is 17 m away.", "source_reference": "OpenStreetMap, Geofabrik extract"},
        {"claim": "Legal records are unavailable.", "source_reference": "Sentinel-2 L2A (Microsoft Planetary Computer)"},
        {"claim": "Legal safety is unavailable.", "source_reference": "legal_safety"},
        {"claim": "Legal safety is unavailable.", "source_reference": "legal_safety factor"}]})
    assert [c["source_reference"] for c in result["citations"]] == ["OpenStreetMap, Geofabrik extract"]


def test_invented_source_still_rejects(monkeypatch):
    with pytest.raises(RuntimeError, match="not in the collected evidence"):
        _answer(monkeypatch, {"answer_text": "Road access is good.", "citations": [
            {"claim": "Nearest mapped road 17 m.", "source_reference": "Tamil Nadu road atlas 2024"}]})


def test_unicode_spaces_in_a_source_still_match(monkeypatch):
    result, _ = _answer(monkeypatch, {"answer_text": "Road 17 m away.", "citations": [
        {"claim": "Nearest mapped road 17 m away.", "source_reference": "OpenStreetMap, Geofabrik extract"}]})
    assert result["citations"][0]["source_reference"] == "OpenStreetMap, Geofabrik extract"


def test_long_text_ends_on_a_whole_sentence():
    text = "First sentence is here. " * 50
    clipped = land_analyst._clip_sentences(text.strip(), 100)
    assert len(clipped) <= 100 and clipped.endswith(".")
