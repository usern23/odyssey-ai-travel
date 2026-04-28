from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel


class TripResponse(BaseModel):
    model_config = {'from_attributes': True}

    id: int
    user_id: int
    name: str
    destination: Optional[str] = None
    origin: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    trip_profile: dict = {}
    generated_plan: Optional[dict] = None
