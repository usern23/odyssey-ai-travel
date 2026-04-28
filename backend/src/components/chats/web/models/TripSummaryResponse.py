from datetime import date
from typing import Optional
from pydantic import BaseModel


class TripSummaryResponse(BaseModel):
    id: int
    name: str
    destination: Optional[str] = None
    origin: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    budget: Optional[str] = None
    has_plan: bool = False

    model_config = {"from_attributes": True}
