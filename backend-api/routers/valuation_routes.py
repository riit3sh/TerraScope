"""Market valuation routes.

Kept separate from the evaluation routes on purpose: valuation answers "what is
this land worth", suitability answers "how well does it suit you". The two must
not be able to move each other.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from valuation.predict import ValuationUnavailable, data_status, estimate_value


LOGGER = logging.getLogger(__name__)
router = APIRouter()

# A refusal is a real answer, not a server fault, so these return 200 with an
# explicit status rather than an error the UI has to guess at.
_BAD_REQUEST_REASONS = {"invalid_input"}


class ValuationRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    area_sqft: float = Field(gt=0)
    land_use: str = "residential"
    # asking (listings), transaction (registered sales) or guideline (government rates)
    price_basis: str = "asking"
    valuation_date: date | None = None


@router.get("/api/v1/valuation/data")
def get_valuation_data() -> dict[str, Any]:
    """Which price observations are loaded, from which sources, and their validation status."""
    return data_status()


@router.post("/api/v1/valuation/estimate")
def post_valuation_estimate(request: ValuationRequest) -> dict[str, Any]:
    try:
        return estimate_value(
            latitude=request.latitude,
            longitude=request.longitude,
            area_sqft=request.area_sqft,
            land_use=request.land_use,
            price_basis=request.price_basis,
            valuation_date=request.valuation_date,
        )
    except ValuationUnavailable as error:
        if error.reason in _BAD_REQUEST_REASONS:
            raise HTTPException(status_code=400, detail=error.detail) from error
        return {"status": "unavailable", "reason": error.reason, "detail": error.detail}
    except Exception as error:  # a broken model must not take the report down
        LOGGER.exception("Valuation failed unexpectedly")
        return {
            "status": "unavailable",
            "reason": "valuation_error",
            "detail": f"The valuation could not be computed: {error}",
        }
