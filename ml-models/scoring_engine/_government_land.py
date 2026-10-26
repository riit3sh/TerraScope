"""Government and restricted land: one status from mapped facilities and the buyer's official-record checks.

Mapping (OpenStreetMap) can only raise a question; it never settles ownership either way. Ownership and restrictions
come from official records the buyer checked and recorded (TerraScope reads none itself). The status decides the verdict
before any score is considered, so a high location or development score cannot override it:

  confirmed_government            a record shows non-transferable government land          -> WALK AWAY
  restricted                      a record shows a restriction that prohibits the use      -> WALK AWAY
  government_transfer_documented  government land with a documented lawful auction/transfer -> at most WAIT
  restricted_with_conditions      a restriction that allows the use on conditions (e.g. NOC) -> at most WAIT
  records_conflicting             official records disagree                                 -> at most WAIT
  potential_public                the boundary overlaps or touches mapped public land       -> at most WAIT, warning
  private_per_record              one record shows private land (not a title guarantee)     -> no hold, unless mapped overlap
  records_unavailable             the buyer could not get the record                        -> as unverified
  ownership_unverified            nothing checked; no mapped overlap (absence is not proof)  -> no hold
"""

from __future__ import annotations

from typing import Any

GOVERNMENT = {"government_non_transferable", "government_transfer_documented"}
# Land a buyer cannot normally acquire: a material mapped overlap with one of these makes the answer RESTRICTED and the
# report stops there (user decision, 2026-10-26). Stadiums, government schools and hospitals stay "potential" (WAIT):
# their owner is not implied by the facility type.
RESTRICTED_CATEGORIES = {"defence", "protected_area", "railway_land", "railway_track", "water_body", "court",
                         "government_office", "park", "burial_ground"}
LABEL = {
    "confirmed_government": "Confirmed government-owned (official record)",
    "restricted": "Restricted: the official record prohibits this use",
    "government_transfer_documented": "Government land with a documented lawful transfer or auction",
    "restricted_with_conditions": "Restricted: allowed only on conditions",
    "records_conflicting": "Official records conflict",
    "potential_public": "Potential government or public land (map only)",
    "private_per_record": "Private according to the record checked",
    "records_unavailable": "Records unavailable",
    "ownership_unverified": "Ownership unverified",
    "restricted_mapped": "Restricted land: the boundary overlaps mapped restricted property",
}


def _cite(r: dict[str, Any]) -> str:
    survey = f", survey {r['survey_number']}" if r.get("survey_number") else ""
    return f"{r.get('source')}{survey}, checked {r.get('checked_on')}"


def government_land_status(record: dict[str, Any]) -> dict[str, Any]:
    records = [r for r in (record.get("user_government_land") or []) if isinstance(r, dict)]
    by_outcome: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        by_outcome.setdefault(r.get("outcome"), []).append(r)
    mapped = record.get("public_land") if isinstance(record.get("public_land"), dict) else {}
    contacts = [i for i in mapped.get("overlaps") or [] if i.get("contact") in ("overlap", "point_inside", "edge")]
    touched = ", ".join(dict.fromkeys(
        f"{i.get('category_label', i.get('category', 'facility')).split(' (')[0].lower()}"
        + (f" ({i['name']})" if i.get("name") else "") for i in contacts[:3]))
    map_note = (f"The boundary overlaps or touches mapped {touched} (OpenStreetMap, ±{mapped.get('uncertainty_m', 15):.0f} m). "
                "That is not an ownership finding." if contacts else "")
    outcomes = set(by_outcome)

    def result(status, *, walk_away=False, hold=False, restricted=False, warning="", would_change=None, checks=None):
        return {"status": status, "label": LABEL[status], "walk_away": walk_away, "hold": hold, "restricted": restricted,
                "warning": warning,
                "would_change": would_change or [], "checks": checks or [], "map_contacts": len(contacts),
                "mapping_status": mapped.get("status") or "not_assessed", "records": len(records)}

    tamil_nadu = ((record.get("location") or {}).get("state") or "").casefold() == "tamil nadu"
    verify = ("Verify the survey number on the Tamil Nadu e-Services 'Verify Government (Poramboke) / Private Land' "
              "service and the A-register, then record the result" if tamil_nadu else
              "Ask the revenue department (taluk office) whether the survey number is government land, using the "
              "state's record of rights, then record the result")
    if outcomes & (GOVERNMENT | {"restriction_prohibits_use", "restriction_with_conditions"}) and "private_per_record" in outcomes:
        cited = "; ".join(_cite(r) for r in records if r.get("outcome") != "records_unavailable")
        return result("records_conflicting", hold=True,
                      warning=f"Official records conflict on government ownership ({cited}).",
                      would_change=["A lawyer reconciling the conflicting records at the taluk office"],
                      checks=["Resolve the conflicting land records with the taluk office and a lawyer before paying"])
    if "restriction_prohibits_use" in outcomes:
        return result("restricted", walk_away=True,
                      warning="you recorded an official restriction that prohibits this use ("
                              + "; ".join(_cite(r) for r in by_outcome["restriction_prohibits_use"]) + ")",
                      would_change=["An official order lifting the restriction for this survey number"])
    if "government_non_transferable" in outcomes:
        return result("confirmed_government", walk_away=True,
                      warning="you recorded an official record showing non-transferable government land ("
                              + "; ".join(_cite(r) for r in by_outcome["government_non_transferable"]) + ")",
                      would_change=["An official order assigning or transferring this land lawfully to the seller"])
    if "government_transfer_documented" in outcomes:
        return result("government_transfer_documented", hold=True,
                      warning="Government land with a documented transfer or auction ("
                              + "; ".join(_cite(r) for r in by_outcome["government_transfer_documented"])
                              + "): buying can be lawful, subject to the order's conditions.",
                      checks=["Have a lawyer verify the auction or assignment order, its conditions (resale bans, "
                              "time limits, payment) and that the seller is the lawful allottee"])
    if "restriction_with_conditions" in outcomes:
        return result("restricted_with_conditions", hold=True,
                      warning="An official restriction allows this use only on conditions ("
                              + "; ".join(_cite(r) for r in by_outcome["restriction_with_conditions"]) + ").",
                      checks=["Obtain the required permission or no-objection certificate before paying"])
    if "private_per_record" in outcomes:
        cited = "; ".join(_cite(r) for r in by_outcome["private_per_record"])
        if contacts:
            return result("private_per_record", hold=True,
                          warning=f"The record you checked shows private land ({cited}), but {map_note[0].lower()}{map_note[1:]}",
                          checks=["Have a licensed surveyor confirm the boundary against the FMB sketch, so the plot is "
                                  "not part of the mapped facility"])
        return result("private_per_record", checks=[f"Private per one record ({cited}); a lawyer still checks the title chain"])
    blocking = [i for i in contacts if i.get("contact") == "overlap" and i.get("category") in RESTRICTED_CATEGORIES]
    if blocking and not records:
        named = ", ".join(dict.fromkeys(
            f"{i.get('category_label', i['category']).split(' (')[0].lower()}" + (f" ({i['name']})" if i.get("name") else "")
            + (f", {i['overlap_share']:.0%} of the plot" if (i.get("overlap_share") or 0) >= 0.01 else
               f", {i['overlap_m2']:,.0f} m² of the plot" if i.get("overlap_m2") else "") for i in blocking[:3]))
        return result("restricted_mapped", restricted=True, hold=True,
                      warning=f"RESTRICTED LAND: the boundary overlaps mapped {named} (OpenStreetMap). "
                              "TerraScope does not assess restricted land for purchase.",
                      would_change=["The authority's written confirmation that the plot lies outside the restricted land"])
    if contacts:
        return result("records_unavailable" if records else "potential_public", hold=True,
                      warning="WARNING: " + map_note + " Verify government or poramboke status before paying.",
                      would_change=["An official record (A-register, poramboke verification) showing the plot is private, "
                                    "and a surveyor's boundary check against the mapped facility"],
                      checks=[verify])
    return result("records_unavailable" if records else "ownership_unverified", checks=[verify])
