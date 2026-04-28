from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class TripCreateRequest(BaseModel):
    name: str
    destination: Optional[str] = None
    origin: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    trip_profile: dict = Field(default_factory=dict)
    generated_plan: dict = Field(default_factory=dict)
