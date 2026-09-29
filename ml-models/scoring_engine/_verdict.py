"""Assemble the verdict from evidence-gated factors."""

from __future__ import annotations

from typing import Any

from ._assessment import (
    assess_accessibility,
    assess_flood,
    assess_growth,
    assess_legal,
)


def build_verdict(
    record: dict[str, Any],
    evaluation: dict[str, Any],
    *,
    weights: dict[str, float],
    legal_risk_score,
    apply_rera_requirement,
    accessibility_score,
    growth_opportunity_score,
    hard_legal_risk_threshold: float,
    buy_threshold: float,
    wait_threshold: float,
) -> dict[str, Any]:
    factors = [
        assess_legal(record, evaluation, legal_risk_score, apply_rera_requirement),
        assess_accessibility(record, evaluation, accessibility_score),
        assess_flood(record),
        assess_growth(record, growth_opportunity_score),
    ]
    for factor in factors:
        factor["weight_pct"] = weights[f"{factor['factor']}_pct"]

    contributions = [
        {"factor": f["factor"], "contribution": round(f["score"] * f["weight_pct"] / 100.0, 2)}
        for f in factors
        if f["score"] is not None
    ]
    # A factor that carries weight but has no evidence blocks the composite.
    # Renormalising over whatever survived would quietly raise the result by
    # dropping the unknowns, which is exactly the inflation to avoid.
    blocking = [f["factor"] for f in factors if f["score"] is None and f["weight_pct"] > 0]
    assessed_weight = round(sum(f["weight_pct"] for f in factors if f["score"] is not None), 2)

    legal = factors[0]
    disqualifying = (
        legal["score"] is not None and (100.0 - legal["score"]) > hard_legal_risk_threshold
    )
    if disqualifying:
        # Proven disqualifying evidence decides on its own. Gaps elsewhere cannot
        # make a parcel with a bad title look merely unassessed.
        return {
            "legal_safety_score": factors[0]["score"],
            "accessibility_score": factors[1]["score"],
            "flood_safety_score": factors[2]["score"],
            "growth_score": factors[3]["score"],
            "weighted_contributions": contributions,
            "composite_score": None,
            "factors": factors,
            "assessed_weight_pct": assessed_weight,
            "unassessed_factors": blocking,
            "recommendation": "AVOID",
            "confidence": None,
            "reasoning_summary": (
                f"AVOID on legal risk alone: effective legal risk {100.0 - legal['score']:.0f}/100 "
                f"exceeds the {hard_legal_risk_threshold:.0f} threshold. "
                + (f"Other factors remain unassessed ({', '.join(blocking)})." if blocking else "")
            )[:500],
        }

    if blocking:
        composite: float | None = None
        recommendation = "INSUFFICIENT_EVIDENCE"
        summary = (
            "Insufficient evidence for a recommendation. No score for: "
            + ", ".join(blocking)
            + f". Only {assessed_weight:.0f}% of the weighting is backed by evidence, "
            "so no BUY/WAIT/AVOID is given."
        )
    else:
        composite = round(sum(item["contribution"] for item in contributions), 2)
        if composite >= buy_threshold:
            recommendation = "BUY"
        elif composite >= wait_threshold:
            recommendation = "WAIT"
        else:
            recommendation = "AVOID"
        summary = (
            f"{recommendation}: composite {composite:.1f} from "
            + "; ".join(f"{f['factor']} {f['score']:.1f}" for f in factors if f["score"] is not None)
            + "."
        )

    return {
        "legal_safety_score": factors[0]["score"],
        "accessibility_score": factors[1]["score"],
        "flood_safety_score": factors[2]["score"],
        "growth_score": factors[3]["score"],
        "weighted_contributions": contributions,
        "composite_score": composite,
        "factors": factors,
        "assessed_weight_pct": assessed_weight,
        "unassessed_factors": blocking,
        "recommendation": recommendation,
        # Percentage confidence is deliberately not emitted. The previous figure
        # multiplied "how many top-level keys are non-null" by distance from 50,
        # which is not a probability of anything. Coverage is reported instead.
        "confidence": None,
        "reasoning_summary": summary[:500],
    }
