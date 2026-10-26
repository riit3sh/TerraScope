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
from ._government_land import government_land_status

LABEL = {"legal_safety": "legal safety", "flood_safety": "flood safety", "growth": "area growth",
         "accessibility": "accessibility"}
# The location factors. A weighted one with no score withholds the decision; legal and flood never do,
# because unscored they become, respectively, the checks before paying and the red flags.
LOCATION_FACTORS = ("growth", "accessibility")
# BUY needs every one of these positively verified in matched land records; a missing value is pending, never clean.
LEGAL_REQUIREMENTS = (("title_clear", True, "title"), ("encumbrance_flag", False, "encumbrance"),
                      ("zoning_verified", True, "zoning"), ("approvals_verified", True, "approvals"))


def _clip(text: str, limit: int = 500) -> str:
    """The schema caps the summary at 500 characters: end on the last whole sentence, never mid-word."""
    if len(text) <= limit:
        return text
    end = text.rfind(". ", 0, limit)
    return text[:end + 1] if end > 0 else text[:limit - 1].rsplit(" ", 1)[0] + "…"


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

    records = record.get("land_records") if isinstance(record.get("land_records"), dict) else {}
    adverse = [text for present, text in ((records.get("title_clear") is False, "the title is not clear"),
                                         (records.get("encumbrance_flag") is True, "an encumbrance is recorded"))
               if present]
    # The buyer's own records (source, date, evidence): a recorded problem counts against buying; a recorded
    # confirmation is named in the reasoning but never satisfies a legal requirement, which needs a matched record.
    user_checks = record.get("user_legal_checks") if isinstance(record.get("user_legal_checks"), dict) else {}
    user_problems = [f"you recorded a problem with the {key if key != 'rera' else 'RERA'} check "
                     f"({r.get('source')}, {r.get('checked_on')})"
                     for key, r in user_checks.items() if isinstance(r, dict) and r.get("outcome") == "problem"]
    pending = [label for key, wanted, label in LEGAL_REQUIREMENTS if records.get(key) is not wanted]
    due_diligence_done = bool(records) and not pending and not adverse
    # Decided before any score: a high location or development score can never override it.
    government = government_land_status(record)
    if government["walk_away"]:
        user_problems.append(government["warning"])

    def pending_text(label: str) -> str:
        mine = user_checks.get(label) if isinstance(user_checks.get(label), dict) else {}
        if mine.get("outcome") == "confirmed":
            return f"{label} (you recorded it as checked on {mine.get('checked_on')}; TerraScope cannot verify that)"
        return label

    legal_pending = ("a lawyer's check of title, a 30-year encumbrance certificate, zoning and approvals against official records"
                     if len(pending) == len(LEGAL_REQUIREMENTS) and not user_checks else
                     "verification of " + ", ".join(pending_text(label) for label in pending) + " against official records")
    if government["restricted"] and not (adverse or user_problems):
        # Mapped restricted property (defence, railway, water body, court...): not assessed for purchase at all.
        recommendation = "RESTRICTED"
        summary = government["warning"]
        would_change = list(government["would_change"])
        composite = None
    elif adverse or user_problems:
        # A matched record showing a defect, or the buyer's own finding of one, is material adverse evidence,
        # whatever the location looks like.
        recommendation = "AVOID"
        summary = ("WALK AWAY: " + ("the matched land records show that " + " and ".join(adverse) if adverse else "")
                   + ("; " if adverse and user_problems else "") + "; ".join(user_problems) + ".")
        would_change = ["Corrected official records showing clear title and no encumbrance" if adverse else
                        government["would_change"][0] if government["walk_away"] else
                        "A lawyer confirming, from the official records, that the recorded problem does not affect this plot"]
        composite = None
    elif legal["score"] is not None and (100.0 - legal["score"]) > hard_legal_risk_threshold:
        # Proven disqualifying evidence decides on its own.
        recommendation = "AVOID"
        summary = (f"WALK AWAY: the matched land records give an effective legal risk of {100.0 - legal['score']:.0f}/100, "
                   f"above the {hard_legal_risk_threshold:.0f} limit.")
        would_change = ["Corrected land records showing clear title and no encumbrance"]
        composite = None
    elif flags:
        # A verified, serious risk is never cancelled out by good access or growth.
        recommendation = "AVOID"
        summary = "WALK AWAY: " + " ".join(flags) + " Do not proceed unless this is explained."
        would_change = ["Official records (local body, revenue department) showing the red flag does not apply to this plot"]
    elif blocking or composite is None:
        recommendation = "INSUFFICIENT_EVIDENCE"
        missing = blocking or [f for f in factors if f["factor"] in LOCATION_FACTORS]
        summary = "INSUFFICIENT DATA: no responsible recommendation yet. " + " ".join(
            f"{LABEL[f['factor']].capitalize()}: {f['basis']}" for f in missing)
        would_change = [f"Evidence for {LABEL[f['factor']]}: {f['checklist'][0] if f.get('checklist') else 'analyse again'}"
                        for f in missing]
    else:
        growth, access = factors[3], factors[1]
        strong = composite >= buy_threshold
        # BUY means strong location evidence AND completed due diligence. Unknown title is never treated as safe,
        # and history alone never makes a BUY: without verified legal checks the answer is WAIT, naming them.
        recommendation = "BUY" if strong and due_diligence_done else "WAIT"
        if recommendation == "BUY":
            lead = "the location evidence is strong and the legal checks are verified from matched land records."
        elif strong:
            lead = "the location evidence is strong, but the required legal checks are not done: " + legal_pending + "."
        else:
            lead = "there is potential, but the location evidence is not strong enough yet."
        parts = [f"{recommendation}: {lead}"]
        trend = (growth.get("details") or {}).get("trend")
        if trend and growth["status"] in ("indicative", "established"):
            level = (f"{trend['first_share']:.1%} ({trend['first_year']}) to {trend['last_share']:.1%} ({trend['last_year']}) "
                     f"built within 1 km, trend {points_a_year(trend['slope_pts_per_year'])} points a year")
            parts.append(("An established, densely built area" if growth["status"] == "established"
                          else growth["basis"].split(":")[0]) + f" (past development, 2017-2023): {level}.")
        road, school = ((access.get("details") or {}).get(k) or {} for k in ("road", "school"))
        if access["score"] is not None:
            def dist(part, name):
                return (f"{name} {part['distance_m']:,.0f} m" if part.get("distance_m") is not None
                        else f"no {name} mapped nearby (not confirmed absent)")
            parts.append(f"Nearest mapped {dist(road, 'road')}, {dist(school, 'school')} (straight line).")
        weakest = min(scored, key=lambda f: f["score"])
        if not strong:
            parts.append(f"Holding it back: {LABEL[weakest['factor']]} {weakest['score']:.0f} of 100.")
        # Second, so the 500-character cap never drops the caveat that the score is not a probability.
        parts.insert(1, f"Location score {composite:.0f} of 100 (strong from {buy_threshold:.0f}; a rule-based score, not a "
                        "probability of appreciation), from " + ", ".join(f"{LABEL[f['factor']]} {f['score']:.0f}" for f in scored) + ".")
        summary = " ".join(parts)
        would_change = []
        if not due_diligence_done:
            would_change.append("Completed legal checks: " + legal_pending)
        if not strong:
            would_change.append(
                f"Stronger {LABEL[weakest['factor']]}: for example an officially sanctioned road, school or other facility "
                "near the plot, with its sanction order (a resident's or broker's claim alone is not enough)")

    checks = checks + government["checks"]
    if government["hold"] and recommendation not in ("AVOID", "RESTRICTED"):
        if recommendation == "BUY":  # mapped or recorded government / restricted land is never bought on a score
            recommendation = "WAIT"
            summary = ("WAIT: the location evidence is strong and the legal checks are verified, but government or "
                       "restricted land must be ruled out first.")
        summary = government["warning"] + " " + summary
        would_change = government["would_change"] + would_change

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
        "reasoning_summary": _clip(summary),
        "red_flags": flags,
        "pre_purchase_checks": checks,
        "would_change": would_change,
        "government_land": government,
    }
