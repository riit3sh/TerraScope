"""One row per thing a buyer needs to know: what was found, how sure, from where, and what to do next.

Built from the evidence snapshot and the scored factors; nothing here adds a figure that is not
already in the snapshot. Each row says how it is known:

- measured: observed by a satellite or mapped data source;
- modelled: a model's scenario (for example river-flood return periods), not an observation;
- user_provided: what the user typed or uploaded, never verified;
- not_verified: TerraScope has no source that could verify it;
- unavailable: the source exists but returned nothing for this parcel.

Assessment is red_flag, caution, ok or unknown. Missing evidence is unknown, never ok.
"""

from __future__ import annotations

from typing import Any

from scoring_engine._assessment import (
    RIVER_FLAG_MAX_RETURN_PERIOD,
    RIVER_FLAG_PARCEL_SHARE,
    WATER_BED_MEAN_OCCURRENCE_PCT,
    parcel_state,
    regional_install_hint,
)

ACCESS_OK_SCORE = 60  # rule, not calibrated: below this the accessibility sub-scores are mostly spent


def _section(record: dict[str, Any], name: str) -> dict[str, Any]:
    value = record.get(name)
    return value if isinstance(value, dict) else {}


def _rows(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out = {}
    for row in record.get("evidence") or []:
        if isinstance(row, dict) and row.get("evidence_id"):
            out[row["evidence_id"].rsplit(":", 1)[-1]] = row
    return out


def _row(area, finding, assessment, basis, next_step, evidence=None, as_of=None, source=None) -> dict[str, Any]:
    return {
        "area": area,
        "finding": finding,
        "assessment": assessment,
        "basis": basis,
        "source": source or (evidence or {}).get("source_reference"),
        "evidence_id": (evidence or {}).get("evidence_id"),
        "as_of": as_of or ((evidence or {}).get("observed_at") or "")[:10] or None,
        "next_step": next_step,
    }


def _legal(record: dict[str, Any], factors: dict[str, dict[str, Any]], state: str | None) -> dict[str, Any]:
    supplied = _section(record, "user_land_details")
    documents = supplied.get("documents") or []
    tamil_nadu = (state or "").casefold() == "tamil nadu"
    where = ("In Tamil Nadu: patta / chitta from eservices.tn.gov.in and the encumbrance certificate from "
             "tnreginet.gov.in. " if tamil_nadu else "")
    if factors.get("legal_safety", {}).get("score") is not None:
        legal = factors["legal_safety"]
        return _row("Title and ownership", legal["basis"], "ok" if legal["score"] >= 70 else "caution", "measured",
                    "Have a lawyer confirm the title chain before paying.")
    finding = "No land record was retrieved, so ownership, encumbrance and approvals are not verified."
    mine = {k: r for k, r in _section(record, "user_legal_checks").items() if isinstance(r, dict)}
    problems = [f"{k} ({r.get('source')}, {r.get('checked_on')})" for k, r in mine.items() if r.get("outcome") == "problem"]
    if problems:  # the buyer's own finding of a defect: the same evidence that makes the verdict WALK AWAY
        return _row("Title and ownership", "You recorded a problem with: " + "; ".join(problems) + ".", "red_flag",
                    "user_provided", "Do not pay. Have a lawyer read the official record; buy only if it shows the "
                    "problem does not affect this plot.", source="Your recorded legal checks")
    confirmed = [k for k, r in mine.items() if r.get("outcome") == "confirmed"]
    if confirmed:
        finding += " You recorded checking " + ", ".join(confirmed) + "; TerraScope cannot verify your records."
    if supplied.get("survey_number"):
        finding += f" You supplied survey {supplied['survey_number']}" + (
            f"/{supplied['subdivision']}" if supplied.get("subdivision") else "") + "."
    if documents:
        finding += f" {len(documents)} document(s) uploaded; they are your claims, not verification."
    return _row("Title and ownership", finding, "unknown", "user_provided" if supplied or mine else "not_verified",
                where + "Get a 30-year encumbrance certificate and the parent documents, and have a lawyer check "
                "the title chain and any loans or court cases on the land.",
                source="No permitted land-records source is integrated")


def _rera(rows: dict[str, dict[str, Any]], record: dict[str, Any], state: str | None) -> dict[str, Any]:
    rera = _section(record, "rera")
    evidence = rows.get("rera")
    portal = " (Tamil Nadu: rera.tn.gov.in)" if (state or "").casefold() == "tamil nadu" else ""
    if rera.get("is_rera_project") is True:
        return _row("RERA registration", f"Registered: {rera.get('rera_registration_number')}.", "ok", "measured",
                    "Check the registration details and completion date on the state RERA portal. Registration does "
                    "not prove title.", evidence)
    return _row("RERA registration",
                "Not checked: the RERA authority for this state is not integrated. RERA applies to plots sold in "
                "a promoter's layout or project.", "unknown", "not_verified",
                f"If a developer is selling this plot in a layout, look it up on the state RERA portal{portal}. "
                "Registration does not prove clear title.", evidence)


def _river(rows: dict[str, dict[str, Any]], flood: dict[str, Any]) -> dict[str, Any]:
    river = _section(flood, "river_flood")
    evidence = rows.get("river-flood")
    scenarios = river.get("scenarios") or []
    if river.get("status") not in ("assessed", "partial") or not scenarios:
        return _row("River flooding", "River flood maps could not be read for this parcel.", "unknown", "unavailable",
                    "Analyse again later; until then treat river flooding as unknown.", evidence)
    on_plot = [s for s in scenarios if (s.get("flooded_share_of_parcel") or 0) > 0]
    first = on_plot[0] if on_plot else None
    if first and first["return_period_years"] <= RIVER_FLAG_MAX_RETURN_PERIOD and first["flooded_share_of_parcel"] >= RIVER_FLAG_PARCEL_SHARE:
        assessment = "red_flag"
    elif first:
        assessment = "caution"
    else:
        hundred = next((s for s in scenarios if s.get("return_period_years") == 100), {})
        assessment = "caution" if (hundred.get("surroundings_flooded_share") or 0) > 0 else "ok"
    if first:
        finding = (f"Modelled river flooding reaches {first['flooded_share_of_parcel']:.0%} of the plot in the "
                   f"1-in-{first['return_period_years']}-year flood ({100 / first['return_period_years']:.3g}% chance "
                   "in any year).")
    elif assessment == "caution":
        finding = "No modelled river flooding on the plot up to 1-in-500 years, but land within 500 m floods at 1-in-100."
    else:
        finding = "No modelled river flooding on the plot or within 500 m in any scenario up to 1-in-500 years."
    next_step = {
        "red_flag": "Do not proceed until neighbours and the local body confirm how often and how deep it floods.",
        "caution": "Ask neighbours and the panchayat or municipality about past floods on this land and its access road.",
        "ok": "The model covers large rivers only (~90 m cells); still ask about monsoon waterlogging.",
    }[assessment]
    return _row("River flooding", finding, assessment, "modelled", next_step, evidence)


def _surface_water(rows: dict[str, dict[str, Any]], flood: dict[str, Any]) -> dict[str, Any]:
    water = _section(flood, "surface_water")
    evidence = rows.get("surface-water")
    inside = _section(water, "parcel")
    if inside.get("water_ever_fraction") is None:
        return _row("Water on the plot, 1984-2021", "Surface-water history could not be read.", "unknown", "unavailable",
                    "Ask whether the plot was ever part of a tank, lake or stream bed.", evidence)
    mean = inside.get("occurrence_mean_pct") or 0
    seen = inside["water_ever_fraction"]
    if mean >= WATER_BED_MEAN_OCCURRENCE_PCT:
        return _row("Water on the plot, 1984-2021",
                    f"Open water was seen on the plot in {mean:.0f}% of satellite passes on average: it may be a "
                    "tank, lake or river bed.", "red_flag", "measured",
                    "Check the revenue records for water-body (poramboke) classification; building there is usually "
                    "prohibited.", evidence)
    return _row("Water on the plot, 1984-2021",
                f"Water was seen at least once on {seen:.0%} of the plot's 30 m pixels.",
                "caution" if seen > 0 else "ok", "measured",
                "Ask why water appears there (a seasonal pond or drain?)." if seen > 0
                else "No action from this source.", evidence)


def _growth(rows: dict[str, dict[str, Any]], factors: dict[str, dict[str, Any]]) -> dict[str, Any]:
    growth = factors.get("growth") or {}
    evidence = rows.get("land-cover")
    if growth.get("status") == "established":
        return _row("Area development", growth["basis"].split(". Further out")[0].split(" The level of")[0], "ok", "measured",
                    "An established, densely built area: little open land is left nearby for new development.",
                    evidence)
    if growth.get("score") is None:
        return _row("Area development", growth.get("basis") or "Area history unavailable.", "unknown", "unavailable",
                    "Analyse the boundary again to collect the 2017-2023 land-cover history.", evidence)
    return _row("Area development", growth["basis"].split(". Further out")[0] + ".",
                "ok" if growth["score"] >= 50 else "caution", "measured",
                "Building around the plot is increasing; on a site visit, see what is being built nearby."
                if growth["score"] >= 50 else
                "Little building nearby: no sign yet of development reaching this area, so there is no hurry.",
                evidence)


def _plot_history(rows: dict[str, dict[str, Any]], record: dict[str, Any]) -> dict[str, Any] | None:
    years = _section(record, "land_cover_history").get("parcel") or []
    if not years:
        return None
    first, last = years[0], years[-1]
    def name(cls: str) -> str:
        return cls.replace("_", " ").replace("built", "built area")
    if any(p["dominant"] in ("water", "flooded_vegetation") for p in years):
        assessment, step = "red_flag", "Confirm the plot is not a water body in the revenue records."
    elif first["dominant"] != last["dominant"]:
        assessment, step = "caution", "Visit the plot: something changed on it; check what stands there and who built it."
    else:
        assessment, step = "ok", "No action from this source."
    finding = (f"The plot was {name(first['dominant'])} in {first['year']} and {name(last['dominant'])} in {last['year']}."
               if first["dominant"] != last["dominant"] else
               f"The plot was {name(first['dominant'])} every year from {first['year']} to {last['year']}.")
    return _row("The plot itself", finding, assessment, "measured", step, rows.get("land-cover"))


def _access(rows: dict[str, dict[str, Any]], factors: dict[str, dict[str, Any]], record: dict[str, Any]) -> dict[str, Any]:
    access = factors.get("accessibility") or {}
    evidence = rows.get("osm")
    details = access.get("details") or {}
    if access.get("score") is None:
        return _row("Road and school access", access.get("basis") or "No infrastructure data for this parcel.",
                    "unknown", "unavailable",
                    f"Run {regional_install_hint(record)} and analyse the boundary again." if regional_install_hint(record)
                    else "Analyse the boundary again; if this persists, check the data-pipeline log.",
                    evidence)
    def where(part: dict[str, Any], label: str) -> str:
        return (f"{label} {part['distance_m']:,.0f} m" if part.get("distance_m") is not None
                else f"no {label} mapped within {(part.get('measured_from') or '').split('within ')[-1].split(' (')[0] or 'the search radius'}")
    finding = f"{where(details['road'], 'road')}, {where(details['school'], 'school')} (straight line, OpenStreetMap)."
    unmapped = [name for name in ("road", "school") if (details.get(name) or {}).get("distance_m") is None]
    step = "Confirm there is a legal, usable access road to the plot itself; a nearby road is not proof of access."
    if unmapped:
        step = (f"No {' or '.join(unmapped)} is mapped nearby, which may only mean OpenStreetMap is incomplete here: "
                f"check locally. {step}")
    return _row("Road and school access", finding[0].upper() + finding[1:],
                "ok" if access["score"] >= ACCESS_OK_SCORE and not unmapped else "caution", "measured", step, evidence)


def build_findings(record: dict[str, Any], factors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every row a buyer should read, red flags first."""
    rows, by_factor = _rows(record), {f["factor"]: f for f in factors}
    state = parcel_state(record)
    flood = _section(record, "flood_indicators")
    findings = [
        _legal(record, by_factor, state),
        _rera(rows, record, state),
        _river(rows, flood),
        _surface_water(rows, flood),
        _row("Rainfall waterlogging and coastal flooding", "Not assessed: no rainfall-drainage or coastal dataset is "
             "integrated.", "unknown", "not_verified",
             "Ask neighbours whether the plot or its road floods after heavy rain."),
        _growth(rows, by_factor),
        _plot_history(rows, record),
        _access(rows, by_factor, record),
    ]
    order = {"red_flag": 0, "caution": 1, "unknown": 2, "ok": 3}
    return sorted((f for f in findings if f), key=lambda f: order[f["assessment"]])
