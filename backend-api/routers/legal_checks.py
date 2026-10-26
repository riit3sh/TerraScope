"""Legal checks: where each one is verified officially, and the buyer's own record of having checked it.

No Indian state publishes a permitted API for title, encumbrance, zoning or approvals (researched 2026-10-26: the
Tamil Nadu portals are interactive web forms, some behind a captcha or a login, and are never scraped). So every state
guide here is manual, and a recorded check is the buyer's statement, shown as theirs. A recorded problem can make the
answer WALK AWAY; a recorded "confirmed" never makes it BUY, because only a matched official record is verification.

A state without a guide gets the generic checklist and an explicit "no state guide yet"; nothing implies it is covered.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from routers.store import get_latest_for_parcel, legal_check_history, save_legal_check

CHECKS = {
    "title": "Title and ownership",
    "encumbrance": "Encumbrance certificate (EC)",
    "zoning": "Zoning / land use",
    "approvals": "Layout and building approvals",
    "rera": "RERA registration (only for plots sold in a promoter's layout or project)",
    "government_land": "Government / poramboke land and restrictions",
}
OUTCOMES = {
    "default": ("confirmed", "problem", "not_found", "not_applicable"),
    # Several official records can be checked for one plot; each is kept per source, so conflicts stay visible.
    "government_land": ("government_non_transferable", "government_transfer_documented", "private_per_record",
                        "restriction_prohibits_use", "restriction_with_conditions", "records_unavailable"),
}
MANDATORY_FOR_BUY = ("title", "encumbrance", "zoning", "approvals")

# One entry per state that has been researched. "automated" stays False until a permitted, documented source exists.
STATE_GUIDES: dict[str, dict[str, dict[str, Any]]] = {
    "tamil nadu": {
        "title": {
            "authority": "Commissionerate of Land Administration, e-Services (patta / chitta, A-register, FMB sketch)",
            "url": "https://eservices.tn.gov.in/",
            "how": "Rural land: district, taluk, village, survey and subdivision number. Urban land: district, town, "
                   "ward, block and survey number (TSLR extract). Check that the owner named on the patta is the "
                   "seller, and verify a web-issued copy by its reference number.",
            "access": "Public web form, no published API. Patta shows revenue ownership, not the full title chain: a "
                      "lawyer still reads the parent documents.",
        },
        "encumbrance": {
            "authority": "Registration Department, TNREGINET (encumbrance certificate search)",
            "url": "https://tnreginet.gov.in/portal/",
            "how": "Search by zone, district, sub-registrar office, village and survey number for at least 30 years. "
                   "Every registered sale, mortgage, lease or court attachment on the survey number should appear.",
            "access": "Online search with a captcha; some services need a user account. No published API. Unregistered "
                      "agreements and some pre-computerisation records do not appear.",
        },
        "zoning": {
            "authority": "Directorate of Town and Country Planning (DTCP); CMDA inside the Chennai metropolitan area",
            "url": "https://tcp.tn.gov.in/",
            "how": "Find the master plan or local planning area plan covering the village and the land-use zone of the "
                   "survey number (residential, agricultural, industrial…). Ask the planning authority or local body "
                   "for a land-use certificate.",
            "access": "Plan documents and maps; no parcel lookup or API was found.",
        },
        "approvals": {
            "authority": "Tamil Nadu single window portal for planning permission (DTCP, CMDA, local bodies)",
            "url": "https://onlineppa.tn.gov.in/",
            "how": "Ask the seller for the layout approval number (DTCP / CMDA / local body) and the approved layout "
                   "plan, and confirm both with the issuing office. Plots in unapproved layouts may need regularisation.",
            "access": "An applicant portal; no public search by survey number or API was found.",
        },
        "rera": {
            "authority": "Tamil Nadu Real Estate Regulatory Authority (TNRERA)",
            "url": "https://rera.tn.gov.in/",
            "how": "If a promoter sells the plot in a layout or project, find it under Registered Projects (building, "
                   "normal layout or regularisation layout) and check its status and completion date.",
            "access": "Public listing pages; no published API, and robots.txt excludes uploaded documents. "
                      "Registration does not prove clear title.",
        },
        "government_land": {
            "authority": "Commissionerate of Land Administration e-Services: 'Verify Government (Poramboke) / Private "
                         "Land', A-register extract and FMB sketch; the taluk office for orders and restrictions",
            "url": "https://eservices.tn.gov.in/",
            "how": "Enter district, taluk, village, survey and subdivision number exactly as on the seller's patta. "
                   "The A-register shows the land's classification (for example ryotwari / patta land or a poramboke "
                   "class such as water body, road or burial ground). For government land being sold, ask for the "
                   "auction or assignment order and its conditions. Near defence or railway land, ask the local "
                   "military authority or the railway division whether a no-objection certificate is needed.",
            "access": "Public web form, no published API; not automated or scraped. One record is not a title "
                      "guarantee: forged patta entries on poramboke land are known, so a lawyer checks the chain.",
        },
    },
}


class LegalCheckRecord(BaseModel):
    """What the buyer (or their lawyer) found on an official source. Stored as their statement, append-only."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    check: Literal["title", "encumbrance", "zoning", "approvals", "rera", "government_land"]
    outcome: Literal["confirmed", "problem", "not_found", "not_applicable", "government_non_transferable",
                     "government_transfer_documented", "private_per_record", "restriction_prohibits_use",
                     "restriction_with_conditions", "records_unavailable"]
    survey_number: str | None = Field(None, max_length=60)
    source: str = Field(min_length=3, max_length=200)  # the portal or office consulted
    checked_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    reference: str | None = Field(None, max_length=120)  # EC / patta / approval / registration number
    evidence: str | None = Field(None, max_length=200)  # e.g. the uploaded document's file name
    notes: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def _applicable(self) -> "LegalCheckRecord":
        if self.outcome not in OUTCOMES.get(self.check, OUTCOMES["default"]):
            raise ValueError(f"{self.outcome} is not an outcome of the {self.check} check.")
        if self.check == "government_land" and not self.survey_number:
            raise ValueError("A government-land check needs the survey number that was looked up.")
        if self.outcome == "not_applicable" and self.check != "rera":
            raise ValueError("Only RERA can be not applicable; title, EC, zoning and approvals always apply.")
        return self


def latest_checks(parcel_id: str) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in legal_check_history(parcel_id):  # oldest first, so the newest record per check wins
        if row["check"] != "government_land":
            latest[row["check"]] = row
    return latest


def government_land_records(parcel_id: str) -> list[dict[str, Any]]:
    """The newest government-land record per official source: two sources that disagree both stay visible."""
    latest: dict[str, dict[str, Any]] = {}
    for row in legal_check_history(parcel_id):
        if row["check"] == "government_land":
            latest[row["source"].strip().casefold()] = row
    return list(latest.values())


def checklist(parcel_id: str, state: str | None) -> dict[str, Any]:
    guide = STATE_GUIDES.get((state or "").strip().casefold())
    latest = latest_checks(parcel_id)
    government = government_land_records(parcel_id)
    return {
        "state": state,
        "state_guide": "available" if guide else "not_yet",
        "automated_sources": [],  # no permitted automated land-record source is integrated for any state
        "notice": ("TerraScope does not read official land records. A check you record here is your statement, shown "
                   "as yours: a recorded problem leads to WALK AWAY, but a recorded confirmation never makes the "
                   "answer BUY. A record you could not find is not a clearance."),
        "checks": [{
            "check": key,
            "label": label,
            "mandatory_for_buy": key in MANDATORY_FOR_BUY,
            "guide": (guide or {}).get(key),
            "record": government[-1] if key == "government_land" and government else latest.get(key),
            "records": government if key == "government_land" else None,
            "outcomes": list(OUTCOMES.get(key, OUTCOMES["default"])),
            "verification": "user_recorded" if (government if key == "government_land" else key in latest) else "not_checked",
        } for key, label in CHECKS.items()],
        "history_count": len(legal_check_history(parcel_id)),
    }


router = APIRouter()


def _state(parcel_id: str) -> str | None:
    latest = get_latest_for_parcel(parcel_id)
    if latest is None:
        raise HTTPException(status_code=404, detail=f"Parcel not found: {parcel_id}")
    return (latest[1].get("location") or {}).get("state")


@router.get("/api/v1/parcels/{parcel_id}/legal-checks")
def read_legal_checks(parcel_id: str) -> dict[str, Any]:
    return checklist(parcel_id, _state(parcel_id))


@router.post("/api/v1/parcels/{parcel_id}/legal-checks")
def record_legal_check(parcel_id: str, record: LegalCheckRecord) -> dict[str, Any]:
    """Append the buyer's record; earlier records are kept. Re-evaluate to see it in the decision."""
    state = _state(parcel_id)
    save_legal_check(parcel_id, record.model_dump(exclude_none=True))
    return checklist(parcel_id, state)
