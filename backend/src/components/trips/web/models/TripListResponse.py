from __future__ import annotations

from pydantic import BaseModel

from src.components.trips.web.models.TripResponse import TripResponse


class TripListResponse(BaseModel):
    items: list[TripResponse]
    total: int
