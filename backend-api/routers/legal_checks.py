"""Legal checks: official sources and the buyer's own record of checking them.

TerraScope has no authorised machine-readable integration for title, encumbrance, zoning,
approvals or RERA. The state guides therefore point the buyer to the relevant official
portal or office without scraping it. A recorded check is the buyer's statement, shown as
theirs. A recorded problem can make the answer WALK AWAY; a recorded "confirmed" never
counts as verification, because only a matched official record is.

A state without a guide gets the generic checklist and an explicit "no state guide yet"; nothing implies it is covered.
"""

from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path
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
    # What the buyer saw on the official RERA portal. No "problem" outcome: a RERA search result alone never means
    # WALK AWAY, and "not found" / "unable to verify" are never proof that a project is unregistered.
    "rera": ("registration_found", "not_found_in_search", "unable_to_verify", "not_applicable"),
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
                     "restriction_with_conditions", "records_unavailable", "registration_found",
                     "not_found_in_search", "unable_to_verify"]
    survey_number: str | None = Field(None, max_length=60)
    source: str = Field(min_length=3, max_length=200)  # the portal or office consulted
    checked_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    reference: str | None = Field(None, max_length=120)  # EC / patta / approval / registration number
    evidence: str | None = Field(None, max_length=200)  # a reference or note supplied by the buyer
    notes: str | None = Field(None, max_length=500)
    # RERA only: the project as the buyer searched it; a registration number's format is never verification.
    project_name: str | None = Field(None, max_length=160)
    promoter_name: str | None = Field(None, max_length=160)
    rera_state: str | None = Field(None, max_length=80)

    @model_validator(mode="after")
    def _applicable(self) -> "LegalCheckRecord":
        if self.outcome not in OUTCOMES.get(self.check, OUTCOMES["default"]):
            raise ValueError(f"{self.outcome} is not an outcome of the {self.check} check.")
        if self.check == "government_land" and not self.survey_number:
            raise ValueError("A government-land check needs the survey number that was looked up.")
        if self.outcome == "not_applicable" and self.check != "rera":
            raise ValueError("Only RERA can be not applicable; title, EC, zoning and approvals always apply.")
        if self.check != "rera" and (self.project_name or self.promoter_name or self.rera_state):
            raise ValueError("Project, promoter and RERA state belong to the RERA check only.")
        if self.outcome == "registration_found" and not (self.reference or self.project_name):
            raise ValueError("A matching registration needs the registration number or the project name you found.")
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


@lru_cache(maxsize=1)
def _official_portals() -> dict[str, dict[str, Any]]:
    """docs/datasets/official_portals.json: MoHUA's RERA list and checked land-record portals. Missing file: no links."""
    path = Path(__file__).resolve().parents[2] / "docs" / "datasets" / "official_portals.json"
    return json.loads(path.read_text(encoding="utf-8"))["regions"] if path.exists() else {}


def _fold(value: str | None) -> str:
    return unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().casefold().strip()


def portal_guide(state: str | None) -> dict[str, dict[str, Any]]:
    """Title and RERA guides for a state without a researched guide: official links only, nothing else claimed."""
    entry = next((e for e in _official_portals().values() if _fold(e["name"]) == _fold(state)), None) if state else None
    if entry is None:
        return {}
    guide: dict[str, dict[str, Any]] = {}
    land = entry.get("land_records") or {}
    if land.get("url"):
        guide["title"] = {"authority": f"{entry['name']} land-records portal ({land.get('title') or 'state revenue department'})",
                          "url": land["url"],
                          "how": "Look up the record of rights for the survey number and check the owner named is the seller; "
                                 "get the encumbrance certificate from the sub-registrar and the 30-year sale-deed chain.",
                          "access": "Checked reachable on 2026-10-27; not researched in detail, never automated. Opening the "
                                    "portal verifies nothing."}
    rera = entry.get("rera") or {}
    if rera.get("url"):
        guide["rera"] = {"authority": f"RERA authority for {entry['name']} (as listed by MoHUA)" + (f"; {rera['note']}" if rera.get("note") else ""),
                         "url": rera["url"],
                         "how": "If a promoter sells the plot in a layout or project, search the project or ask the seller for "
                                "its registration number. A project you cannot find is not proof it is unregistered.",
                         "access": "From MoHUA's list of State/UT RERA authorities (read 2026-10-27); no API, never automated."}
    return guide


def checklist(parcel_id: str, state: str | None) -> dict[str, Any]:
    guide = STATE_GUIDES.get((state or "").strip().casefold())
    researched = guide is not None
    guide = guide or portal_guide(state) or None
    latest = latest_checks(parcel_id)
    government = government_land_records(parcel_id)
    return {
        "state": state,
        "state_guide": "available" if researched else "partial" if guide else "not_yet",
        "automated_sources": [],  # no permitted automated land-record source is integrated for any state
        "notice": ("TerraScope does not read official land records. A check you record here is your statement, shown "
                   "as yours: a recorded problem leads to WALK AWAY; a recorded confirmation is never treated as "
                   "official verification. A record you could not find is not a clearance."),
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


@router.get("/api/v1/rera-authorities")
def rera_authorities() -> dict[str, Any]:
    """Every State/UT RERA authority as MoHUA lists it (36 regions): portal URL, or none where no website is set up."""
    return {"source": "MoHUA list of State/UT RERA authorities, read 2026-10-27",
            "authorities": sorted(({"state": e["name"], **(e.get("rera") or {})} for e in _official_portals().values()),
                                  key=lambda a: a["state"])}


@router.get("/api/v1/parcels/{parcel_id}/legal-checks")
def read_legal_checks(parcel_id: str) -> dict[str, Any]:
    return checklist(parcel_id, _state(parcel_id))


@router.post("/api/v1/parcels/{parcel_id}/legal-checks")
def record_legal_check(parcel_id: str, record: LegalCheckRecord) -> dict[str, Any]:
    """Append the buyer's record; earlier records are kept. Re-evaluate to see it in the decision."""
    state = _state(parcel_id)
    save_legal_check(parcel_id, record.model_dump(exclude_none=True))
    return checklist(parcel_id, state)
