"""Evidence gates for TerraScope scoring.

A score is only emitted when evidence actually supports it. Missing evidence
stays unknown: it is never substituted with 50, and it is never silently dropped
so that the surviving factors renormalise into a better-looking result.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


LEGAL_EVIDENCE_CHECKLIST = (
    "Ownership record matched to this survey / subdivision number",
    "Encumbrance certificate or registered transaction history",
    "Land-use zoning approval or restriction record",
    "Project registration from the parcel's own state authority",
)

MISSING_FLOOD_EVIDENCE = {
    "river_flooding": "River flood hazard map covering this parcel, with resolution and date",
    "historical_inundation": "Observed historical inundation footprints for the parcel vicinity (a permitted machine-readable source)",
    "observed_surface_water": "Observed surface-water history for the parcel and its surroundings",
    "terrain_and_nearby_water": "Elevation relative to the nearest watercourse and drainage network",
    "rainfall_waterlogging": "Rainfall intensity and local drainage capacity, or a pluvial flood model",
    "coastal_flooding": "Storm-surge and sea-level inundation data (relevant near the coast)",
}

FLOOD_EVIDENCE_CHECKLIST = (
    "Flood hazard / inundation extent map covering this parcel, with resolution and date",
    "Historical inundation records for the parcel vicinity",
    "Distance and elevation relative to the nearest watercourse and drainage network",
    "Rainfall intensity and local drainage capacity",
)


def _section(record: dict[str, Any], name: str) -> dict[str, Any]:
    value = record.get(name)
    return value if isinstance(value, dict) else {}


LAND_IDENTIFIER_FIELDS = ("state", "district", "taluk", "village", "survey_number", "subdivision")
DOC_TYPE_LABELS = {
    "patta_chitta": "patta / chitta (ownership record)",
    "encumbrance_certificate": "encumbrance certificate",
    "sale_deed": "sale deed",
    "layout_or_building_approval": "layout or building approval",
    "fmb_sketch": "FMB / survey sketch",
    "other": "other document",
}


def parcel_state(record: dict[str, Any]) -> str | None:
    """The geocoded state, else the boundary file's (polygon-based, so known even without an address)."""
    states = _section(record, "coverage").get("states") or []
    name = _section(record, "location").get("state") or (states[0].get("name") if len(states) == 1 else None)
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode() if name else None


def supplied_summary(details: dict[str, Any]) -> str:
    """One honest sentence about what the user supplied: never 'verified'."""
    ids = {field: details.get(field) for field in LAND_IDENTIFIER_FIELDS if details.get(field)}
    parts = []
    if ids.get("survey_number"):
        survey = ids["survey_number"] + (f"/{ids['subdivision']}" if ids.get("subdivision") else "")
        place = ", ".join(ids[f] for f in ("village", "taluk", "district", "state") if ids.get(f))
        parts.append(f"You supplied survey {survey}" + (f" in {place}" if place else ""))
        missing = [f for f in ("state", "district", "village") if not ids.get(f)]
        if missing:
            parts.append(f"add the {', '.join(missing)}: survey numbers repeat across villages, so the identifier is ambiguous")
    documents = details.get("documents") or []
    if documents:
        listed = []
        for doc in documents:
            found = [f"{m['field'].replace('_', ' ')} on page {', '.join(map(str, m['pages']))}" if m.get("pages")
                     else f"{m['field'].replace('_', ' ')}" for m in doc.get("mentions") or []]
            listed.append(f"{doc['filename']} ({DOC_TYPE_LABELS.get(doc.get('doc_type'), 'type not given')}"
                          + (f"; mentions {', '.join(found)}" if found else "") + ")")
        parts.append("documents: " + "; ".join(listed))
    if not parts:
        return ""
    return "; ".join(parts) + ". These are user-provided and not independently verified, so title is not verified."


def land_records_matched(record: dict[str, Any]) -> bool:
    """True only when an authoritative record was actually retrieved and matched."""
    records = record.get("land_records")
    if not isinstance(records, dict):
        return False
    return any(
        records.get(field) is not None
        for field in ("survey_number", "ownership_type", "title_clear", "encumbrance_flag")
    )


def assess_legal(
    record: dict[str, Any],
    evaluation: dict[str, Any],
    legal_risk_score,
    apply_rera_requirement,
) -> dict[str, Any]:
    """Legal safety, or an explicit incomplete verification with a checklist.

    No ownership, encumbrance, restriction or state registration source is
    integrated. Absence of records is not evidence of clear title, so no number
    is produced from it.
    """
    if not land_records_matched(record):
        state = parcel_state(record) or "this parcel's state"
        supplied = _section(record, "user_land_details")
        basis = (
            "Legal verification incomplete: no authoritative land record was retrieved or matched for this parcel "
            f"({state}). Absence of records is not evidence of clear title."
        )
        if supplied:
            basis += " " + supplied_summary(supplied)
        return {
            "factor": "legal_safety",
            "score": None,
            "status": "unavailable",
            "basis": basis,
            "limitations": (
                "No ownership, encumbrance, restriction or land-use approval source is integrated, and no dataset "
                f"from the RERA authority for {state} is. Documents you upload are recorded as your claims: "
                "TerraScope can show where an identifier appears in them, but that never verifies title."
            ),
            "checklist": list(LEGAL_EVIDENCE_CHECKLIST),
            "details": supplied or None,
        }
    scoring_record = {**record, "evaluation": evaluation}
    risk = min(100.0, legal_risk_score(scoring_record) + apply_rera_requirement(record, evaluation)["penalty"])
    return {
        "factor": "legal_safety",
        "score": round(100.0 - risk, 2),
        "status": "assessed",
        "basis": f"Scored from matched land records; effective legal risk {risk:.1f}/100.",
        "limitations": "Project-registration matching is district-level and limited to the seeded state.",
        "checklist": [],
    }


def assess_flood(record: dict[str, Any]) -> dict[str, Any]:
    """Flood safety is scored only when a validated source populates risk.flood_risk_score.

    Nothing does today: the ETL leaves that field null. When per-mechanism flood
    evidence exists (modelled river flooding, observed surface water, terrain) the
    factor is "partial" with that evidence in its basis and NO score; otherwise it is
    "unavailable". The terrain-position indicator must never populate the score.
    """
    risk = _section(record, "risk")
    hazard = risk.get("flood_risk_score")
    if isinstance(hazard, (int, float)):
        return {
            "factor": "flood_safety",
            "score": round(max(0.0, min(100.0, 100.0 - float(hazard))), 2),
            "status": "assessed",
            "basis": risk.get("flood_risk_basis") or f"From an integrated flood hazard source (risk {hazard}/100).",
            "limitations": "Check the source's resolution, coverage and observation date.",
            "checklist": [],
        }
    indicators = _section(record, "flood_indicators")
    components = [c for c in (indicators.get("components") or []) if isinstance(c, dict)]
    usable = [c for c in components if c.get("status") in ("assessed", "partial")]
    if usable:
        # Real evidence for some mechanisms. It is shown, mechanism by mechanism, but no
        # validated method combines it into a safety score, so the score stays withheld
        # (and a missing mechanism can never be read as a perfect one).
        river = next((c for c in components if c.get("mechanism") == "river_flooding"), {})
        missing = [
            c["mechanism"].replace("_", " ") for c in components
            if c.get("status") not in ("assessed", "partial")
        ]
        # The flood panel carries the measurements; this line only says what was and was not assessed.
        head = ("River flood exposure assessed (modelled scenarios, ~90 m)" if river.get("status") in ("assessed", "partial")
                else "River flood exposure not assessed")
        others = [c["mechanism"].replace("_", " ") for c in usable if c.get("mechanism") != "river_flooding"]
        basis = head + ("; also measured: " + ", ".join(others) if others else "")
        basis += ("; other mechanisms incomplete (" + ", ".join(missing) + ")." if missing else ".")
        return {
            "factor": "flood_safety",
            "score": None,
            "status": "partial",
            "basis": basis,
            "limitations": (
                "No overall Flood Safety score: no validated method combines the mechanisms, and a mechanism that "
                "is not assessed is unknown, not safe. Measurements and caveats are in the flood section."
            ),
            # What is still missing, not a generic list that includes what was just measured.
            "checklist": [MISSING_FLOOD_EVIDENCE[c["mechanism"]] for c in components
                          if c.get("status") not in ("assessed", "partial", "not_applicable") and c.get("mechanism") in MISSING_FLOOD_EVIDENCE],
        }
    return {
        "factor": "flood_safety",
        "score": None,
        "status": "unavailable",
        "basis": "No usable flood evidence was retrieved for this parcel: every flood source was unavailable or not integrated.",
        "limitations": (
            "Coastal, fluvial (river) and pluvial (rainfall/drainage) flooding are distinct and none is "
            "assessed here. Missing evidence is unknown, not safe. Being inland does not establish safety, and "
            "district flood history would not establish risk for this individual plot."
        ),
        "checklist": list(FLOOD_EVIDENCE_CHECKLIST),
    }


# Rules, not calibrated against prices: +2 points of built land a year within 1 km scores 100, and a ring
# that was already this built in the first year has no open land left to show a trend.
GROWTH_FULL_SCORE_PTS_PER_YEAR = 2.0
# Provisional, not validated: a 1 km ring at least this built, gaining under STEADY points a year, is an
# established area (not scored). FAST / STEADY only name the pace in the text.
DENSE_SHARE = 0.75
FAST_PTS_PER_YEAR = 1.5
STEADY_PTS_PER_YEAR = 0.5
# Red flags that stop a purchase whatever the other factors say.
RIVER_FLAG_MAX_RETURN_PERIOD = 100
RIVER_FLAG_PARCEL_SHARE = 0.25
WATER_BED_MEAN_OCCURRENCE_PCT = 10.0
# Provisional rules, not validated (user decision, 2026-10-28). When the river flood maps were not read, the flood
# history becomes a check before paying, and these local water signs alone hold a BUY at WAIT: ground at or below the
# nearest mapped water, or open water seen at least once on this share of the plot's 30 m pixels (1984-2021).
FLOOD_LOW_GROUND_M = 0.0
FLOOD_WATER_SEEN_SHARE = 0.10

AREA_HISTORY_LIMITS = (
    "Built-area share from a 10 m machine-learning land-cover map (Impact Observatory / Esri, 2017-2023). It shows "
    "development on the ground, not prices, approvals or planned infrastructure. Single years can be misclassified, "
    "so the least-squares trend over every year is used. Scoring rule, not calibrated: +2 points a year scores 100."
)


def built_level(share: float) -> str:
    """How built-up the 1 km ring is, in words: the level, never the pace (SRM, 2026-10-28: a ring 67% built
    was called "Little or no development" because only its pace was low)."""
    if share >= DENSE_SHARE:
        return "Densely built area"
    if share >= 0.5:
        return "Largely built-up area"
    if share >= 0.25:
        return "Partly built-up area"
    return "Sparsely built area"


def built_pace(slope: float) -> str:
    return ("fast new building" if slope >= FAST_PTS_PER_YEAR else "steady new building" if slope >= STEADY_PTS_PER_YEAR
            else "little new building")


def points_a_year(slope: float) -> str:
    """'+1.9', '-0.3' or '0.0': rounded first, so a -0.04 or float-noise slope never prints as '-0.0'."""
    value = round(slope, 1) + 0.0
    return f"{value:+.1f}" if value else "0.0"


def _built_change(trend: dict[str, Any], where: str) -> str:
    # The endpoints and the trend answer different questions: the trend is a least-squares fit through every
    # year, so a dip in the middle years can make it flat even when the last year is higher than the first.
    return (f"built-up land {where} was {trend['first_share']:.1%} in {trend['first_year']} and "
            f"{trend['last_share']:.1%} in {trend['last_year']}; the trend across all {trend['years_used']} years is "
            f"{points_a_year(trend['slope_pts_per_year'])} points a year")


def assess_growth(record: dict[str, Any], growth_opportunity_score) -> dict[str, Any]:
    """How fast the land around the parcel has been built up, 2017-2023.

    The parcel's own Sentinel-2 change is not used: land cover changing on one plot cannot separate
    construction from cropping. The surroundings' built-area trend over seven annual maps is the
    development history the buy/wait decision rests on.
    """
    history = _section(record, "land_cover_history")
    near, far = history.get("trend_within_1km"), history.get("trend_1_to_3km")
    if not history:
        return {
            "factor": "growth",
            "score": None,
            "status": "unavailable",
            "basis": "This report was made before TerraScope read the area's development history (land cover "
                     "2017-2023 around the plot). Analyse the same boundary again to add it.",
            "limitations": AREA_HISTORY_LIMITS,
            "checklist": ["Area development history: analyse the boundary again"],
        }
    if history.get("status") != "assessed" or not near:
        return {
            "factor": "growth",
            "score": None,
            "status": "unavailable",
            "basis": "Area development history unavailable: "
                     + (history.get("error") or "too few years were classified around the plot."),
            "limitations": AREA_HISTORY_LIMITS,
            "checklist": ["Area development history: analyse the boundary again"],
        }
    slope = near["slope_pts_per_year"]
    further = f" Further out, {_built_change(far, '1-3 km away')}." if far else ""
    # Level and rate answer different questions. A ring that is already dense, with little new building, is an
    # established area: its low rate is not a weakness of the plot, so it is described but neither scored nor
    # penalised, and the decision rests on access and risks. A dense ring still building fast is scored normally.
    if near["last_share"] >= DENSE_SHARE and slope < STEADY_PTS_PER_YEAR:
        return {
            "factor": "growth",
            "score": None,
            "status": "established",
            "basis": f"Established, densely built area: {_built_change(near, 'within 1 km')}.{further} The level of "
                     "development is neither scored for nor against the decision; it rests on access and risks.",
            "limitations": AREA_HISTORY_LIMITS,
            "checklist": [],
            "details": {"trend": near, "ring": "within 1 km"},
        }
    # The headline names the level and the pace separately; the score still follows the pace only.
    headline = f"{built_level(near['last_share'])} ({near['last_share']:.0%} within 1 km), {built_pace(slope)} since 2017"
    return {
        "factor": "growth",
        "score": round(max(0.0, min(100.0, 100.0 * slope / GROWTH_FULL_SCORE_PTS_PER_YEAR)), 2),
        "status": "indicative",
        "basis": f"{headline}: {_built_change(near, 'within 1 km')}.{further}",
        "limitations": AREA_HISTORY_LIMITS,
        "checklist": [],
        "details": {"trend": near, "ring": "within 1 km"},
    }


def red_flags(record: dict[str, Any]) -> list[str]:
    """History that argues against buying at all: frequent modelled river flooding, or a likely water bed."""
    flags = []
    flood = _section(record, "flood_indicators")
    for scenario in _section(flood, "river_flood").get("scenarios") or []:  # most frequent first
        period, share = scenario.get("return_period_years"), scenario.get("flooded_share_of_parcel") or 0
        if period and period <= RIVER_FLAG_MAX_RETURN_PERIOD and share >= RIVER_FLAG_PARCEL_SHARE:
            flags.append(f"Modelled river flooding covers {share:.0%} of the plot in the 1-in-{period}-year flood "
                         f"({100 / period:.3g}% chance in any year).")
            break
    water = _section(_section(flood, "surface_water"), "parcel")
    if (water.get("occurrence_mean_pct") or 0) >= WATER_BED_MEAN_OCCURRENCE_PCT:
        flags.append(f"Open water was seen on this plot in {water['occurrence_mean_pct']:.0f}% of satellite passes "
                     "from 1984 to 2021: it may be a tank, lake or river bed.")
    wet = [str(p["year"]) for p in _section(record, "land_cover_history").get("parcel") or []
           if p.get("dominant") in ("water", "flooded_vegetation")]
    if wet:
        flags.append(f"The plot was mapped as water or flooded vegetation in {', '.join(wet)}.")
    return flags


def unassessed_flood(record: dict[str, Any]) -> dict[str, Any] | None:
    """None when the river flood maps were read; otherwise the check before paying and any strong local water signs."""
    flood = _section(record, "flood_indicators")
    river = flood.get("river_flood")
    if isinstance(river, dict) and river.get("status") in ("assessed", "partial"):
        return None
    signs = []
    terrain = _section(flood, "terrain")
    height = terrain.get("elevation_above_nearest_water_m")
    if isinstance(height, (int, float)) and height <= FLOOD_LOW_GROUND_M:
        near = terrain.get("nearest_water_feature_class") or terrain.get("nearest_water_feature_kind") or "water"
        away = terrain.get("nearest_water_feature_distance_m")
        signs.append(f"the plot's ground is {height:+.1f} m relative to the nearest mapped water ({near}"
                     + (f", {away:,.0f} m away)" if isinstance(away, (int, float)) else ")"))
    seen = _section(_section(flood, "surface_water"), "parcel").get("water_ever_fraction")
    if isinstance(seen, (int, float)) and seen >= FLOOD_WATER_SEEN_SHARE:
        signs.append(f"open water was seen at least once on {seen:.0%} of the plot's 30 m pixels (1984-2021)")
    return {
        "strong": bool(signs),
        "signs": signs,
        "check": "Flood history: river flood maps were not read for this report. Ask neighbours and the local body "
                 "whether the plot flooded or waterlogged in recent monsoons, and see the plot after heavy rain",
    }


def plot_history_checks(record: dict[str, Any]) -> list[str]:
    """What the plot itself became over the years, when that changed: something to see before paying."""
    years = _section(record, "land_cover_history").get("parcel") or []
    if len(years) < 2 or years[0]["dominant"] == years[-1]["dominant"]:
        return []
    def name(cls: str) -> str:
        return cls.replace("_", " ").replace("built", "built area")
    return [f"The plot itself changed from {name(years[0]['dominant'])} ({years[0]['year']}) to "
            f"{name(years[-1]['dominant'])} ({years[-1]['year']}): see what stands on it today."]


def _metres(value: Any) -> str:
    return f"{value:,.0f} m" if isinstance(value, (int, float)) else "not found"


def regional_install_hint(record: dict[str, Any]) -> str | None:
    """The exact `terrascope.cmd fetch-data <region>` the collector recorded when no regional store was installed."""
    for row in record.get("evidence") or []:
        if isinstance(row, dict) and row.get("source_type") == "openstreetmap":
            match = re.search(r"terrascope\.cmd fetch-data [a-z0-9-]+", row.get("summary") or "")
            if match:
                return match.group(0)
    return None


def assess_accessibility(
    record: dict[str, Any],
    evaluation: dict[str, Any],
    accessibility_components,
) -> dict[str, Any]:
    """Proximity from OpenStreetMap under the user's distance limits, flagged as straight-line."""
    infrastructure = _section(record, "infrastructure")
    if infrastructure.get("nearest_road_distance_m") is None and infrastructure.get("nearest_school_distance_m") is None             and infrastructure.get("search_radius_m") is None:
        return {
            "factor": "accessibility",
            "score": None,
            "status": "unavailable",
            "basis": (f"Accessibility unavailable: no regional OpenStreetMap data is installed for "
                      f"{parcel_state(record) or 'this state'}. Install it with {hint} and analyse again."
                      if (hint := regional_install_hint(record)) else
                      "Accessibility unavailable: no infrastructure was retrieved for this parcel."),
            "limitations": "The OpenStreetMap lookup returned nothing usable, or failed.",
            "checklist": ["Regional OpenStreetMap data covering this parcel"],
            "details": None,
        }
    if (infrastructure.get("layer_status") or {}).get("road") == "not_installed":
        # Scoring access from schools alone would hide the missing road data: the factor stays unknown.
        return {
            "factor": "accessibility",
            "score": None,
            "status": "unavailable",
            "basis": (f"Accessibility unavailable: road data is not installed for {parcel_state(record) or 'this state'}. "
                      "The all-India store has water, schools, hospitals, transport stops and public facilities, but no "
                      "roads. Build the state's roads with "
                      + (regional_install_hint(record) or "terrascope.cmd fetch-data "
                         + (re.sub(r"[^a-z0-9]+", "-", (parcel_state(record) or "<state>").lower()).strip("-") or "<state>"))
                      + " and analyse again."),
            "limitations": "Unknown, not absent: no road distance is reported rather than an estimated one.",
            "checklist": ["Regional road data for this state"],
            "details": None,
        }
    parts = accessibility_components({**record, "evaluation": evaluation}, _section(evaluation, "preferences"))

    def describe(name: str, part: dict[str, Any]) -> str:
        if part["distance_m"] is None:
            return (f"{name}: {part['measured_from']}, so it is left out of the score"
                    if part["measured_from"].startswith("none mapped") else f"{name}: not found, so it is left out")
        centroid = (f" ({_metres(part['centroid_distance_m'])} from the centroid)"
                    if part["measured_from"] == "parcel boundary" and part["centroid_distance_m"] is not None else "")
        return (f"{name} {_metres(part['distance_m'])} from the {part['measured_from']}{centroid}: "
                f"{part['sub_score']:.0f}/100 against your {part['cap_m']:,.0f} m limit")

    return {
        "factor": "accessibility",
        "score": parts["score"],
        "status": "indicative" if parts["score"] is not None else "unavailable",
        "basis": (
            f"{describe('Nearest mapped road', parts['road'])}; {describe('nearest mapped school', parts['school'])}. "
            f"Weighted road x{parts['road']['weight']:g}, school x{parts['school']['weight']:g} "
            "(property type and your importance settings). A sub-score falls linearly to 0 at your limit."
        ),
        "limitations": (
            "Straight-line distances to OpenStreetMap geometry, not routed travel distances. A nearby road is not "
            "proof of legal or physical access, and OpenStreetMap can miss schools. The drawn boundary is not a "
            "cadastral boundary."
        ),
        "checklist": [] if parts["score"] is not None else ["Regional OpenStreetMap data covering this parcel"],
        "details": parts,
    }
