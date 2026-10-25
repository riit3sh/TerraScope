"""Assemble the buy / wait decision from evidence-gated factors."""

from __future__ import annotations

from typing import Any

from ._assessment import (
    assess_accessibility,
    assess_flood,
    assess_growth,
    assess_legal,
    plot_history_checks,
    points_a_year,
    red_flags,
)

LABEL = {"legal_safety": "legal safety", "flood_safety": "flood safety", "growth": "area growth",
         "accessibility": "accessibility"}
# The location factors. A weighted one with no score withholds the decision; legal and flood never do,
# because unscored they become, respectively, the checks before paying and the red flags.
LOCATION_FACTORS = ("growth", "accessibility")


def build_verdict(
    record: dict[str, Any],
    evaluation: dict[str, Any],
    *,
    weights: dict[str, float],
    legal_risk_score,
    apply_rera_requirement,
    accessibility_components,
    growth_opportunity_score,
    hard_legal_risk_threshold: float,
    buy_threshold: float,
) -> dict[str, Any]:
    factors = [
        assess_legal(record, evaluation, legal_risk_score, apply_rera_requirement),
        assess_accessibility(record, evaluation, accessibility_components),
        assess_flood(record),
        assess_growth(record, growth_opportunity_score),
    ]
    for factor in factors:
        factor["weight_pct"] = weights[f"{factor['factor']}_pct"]
    legal = factors[0]

    scored = [f for f in factors if f["score"] is not None and f["weight_pct"] > 0]
    scored_weight = round(sum(f["weight_pct"] for f in scored), 2)
    # Shares of the scored weight, so contributions add up to the composite. Unscored legal and flood are
    # not quietly dropped: they come back as checks and red flags beside the decision.
    contributions = [{"factor": f["factor"], "contribution": round(f["score"] * f["weight_pct"] / scored_weight, 2)}
                     for f in scored]
    blocking = [f for f in factors if f["factor"] in LOCATION_FACTORS and f["score"] is None
                and f["weight_pct"] > 0 and f["status"] != "established"]
    flags = red_flags(record)
    checks = (legal["checklist"] if legal["score"] is None else []) + plot_history_checks(record)
    composite = round(sum(c["contribution"] for c in contributions), 2) if scored and not blocking else None

    if legal["score"] is not None and (100.0 - legal["score"]) > hard_legal_risk_threshold:
        # Proven disqualifying evidence decides on its own.
        recommendation = "AVOID"
        summary = (f"WALK AWAY: the matched land records give an effective legal risk of {100.0 - legal['score']:.0f}/100, "
                   f"above the {hard_legal_risk_threshold:.0f} limit.")
        composite = None
    elif flags:
        # A verified, serious risk is never cancelled out by good access or growth.
        recommendation = "AVOID"
        summary = "WALK AWAY: " + " ".join(flags) + " Do not proceed unless this is explained."
    elif blocking or composite is None:
        recommendation = "INSUFFICIENT_EVIDENCE"
        missing = blocking or [f for f in factors if f["factor"] in LOCATION_FACTORS]
        summary = "INSUFFICIENT DATA: no responsible recommendation yet. " + " ".join(
            f"{LABEL[f['factor']].capitalize()}: {f['basis']}" for f in missing)
    else:
        recommendation = "BUY" if composite >= buy_threshold else "WAIT"
        growth, access = factors[3], factors[1]
        parts = [f"{recommendation}: " + ("the evidence TerraScope can check supports proceeding." if recommendation == "BUY"
                                          else "there is potential, but the evidence does not support buying yet.")]
        trend = (growth.get("details") or {}).get("trend")
        if trend and growth["status"] in ("indicative", "established"):
            level = (f"{trend['first_share']:.1%} ({trend['first_year']}) to {trend['last_share']:.1%} ({trend['last_year']}) "
                     f"built within 1 km, trend {points_a_year(trend['slope_pts_per_year'])} points a year")
            parts.append(("An established, densely built area" if growth["status"] == "established"
                          else growth["basis"].split(":")[0]) + f": {level}.")
        road, school = ((access.get("details") or {}).get(k) or {} for k in ("road", "school"))
        if access["score"] is not None:
            def dist(part, name):
                return f"{name} {part['distance_m']:,.0f} m" if part.get("distance_m") is not None else f"no {name} found"
            parts.append(f"Nearest mapped {dist(road, 'road')}, {dist(school, 'school')} (straight line).")
        if recommendation == "WAIT":
            weakest = min(scored, key=lambda f: f["score"])
            parts.append(f"Holding it back: {LABEL[weakest['factor']]} {weakest['score']:.0f} of 100.")
        parts.append(f"Composite {composite:.0f} of 100 (BUY from {buy_threshold:.0f}) from "
                     + ", ".join(f"{LABEL[f['factor']]} {f['score']:.0f}" for f in scored) + ".")
        if legal["score"] is None:
            parts.append("Title, encumbrance, approvals and RERA are not verified: confirm them before paying.")
        summary = " ".join(parts)

    return {
        "legal_safety_score": factors[0]["score"],
        "accessibility_score": factors[1]["score"],
        "flood_safety_score": factors[2]["score"],
        "growth_score": factors[3]["score"],
        "weighted_contributions": contributions,
        "composite_score": composite,
        "factors": factors,
        "assessed_weight_pct": scored_weight,
        "unassessed_factors": [f["factor"] for f in factors if f["score"] is None and f["weight_pct"] > 0],
        "recommendation": recommendation,
        # Percentage confidence is deliberately not emitted: no figure here is a probability of anything.
        "confidence": None,
        "reasoning_summary": summary[:500],
        "red_flags": flags,
        "pre_purchase_checks": checks,
    }
