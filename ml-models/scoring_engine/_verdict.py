"""Assemble the buy / wait decision from evidence-gated factors."""

from __future__ import annotations

from typing import Any

from ._assessment import (
    assess_accessibility,
    assess_flood,
    assess_growth,
    assess_legal,
    plot_history_checks,
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
                and f["weight_pct"] > 0 and f["status"] != "built_out"]
    flags = red_flags(record)
    checks = (legal["checklist"] if legal["score"] is None else []) + plot_history_checks(record)
    composite = round(sum(c["contribution"] for c in contributions), 2) if scored and not blocking else None

    if legal["score"] is not None and (100.0 - legal["score"]) > hard_legal_risk_threshold:
        # Proven disqualifying evidence decides on its own.
        recommendation = "AVOID"
        summary = (f"AVOID on legal risk alone: effective legal risk {100.0 - legal['score']:.0f}/100 exceeds the "
                   f"{hard_legal_risk_threshold:.0f} threshold.")
        composite = None
    elif flags:
        recommendation = "AVOID"
        summary = "AVOID: " + " ".join(flags)
    elif blocking or composite is None:
        recommendation = "INSUFFICIENT_EVIDENCE"
        missing = blocking or [f for f in factors if f["factor"] in LOCATION_FACTORS]
        summary = "No buy/wait decision yet. " + " ".join(f"{LABEL[f['factor']].capitalize()}: {f['basis']}" for f in missing)
    else:
        recommendation = "BUY" if composite >= buy_threshold else "WAIT"
        growth = factors[3]
        parts = [f"{recommendation}: composite {composite:.0f} of 100 (BUY from {buy_threshold:.0f}) from "
                 + ", ".join(f"{LABEL[f['factor']]} {f['score']:.0f}" for f in scored) + "."]
        if growth["status"] in ("indicative", "built_out"):
            parts.append(growth["basis"].split(". Further out")[0].rstrip(".") + ".")
        if recommendation == "WAIT":
            weakest = min(scored, key=lambda f: f["score"])
            parts.append(f"Holding it back: {LABEL[weakest['factor']]} {weakest['score']:.0f}.")
        if legal["score"] is None:
            parts.append("Before paying, check title, encumbrance and approvals: TerraScope cannot verify them.")
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
