from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from src.components.chats.web.models.TripSummaryResponse import TripSummaryResponse


class ChatResponse(BaseModel):
    id: int
    title: str
    status: str
    trip_id: Optional[int] = None
    trip: Optional[TripSummaryResponse] = None
    created_at: datetime
    updated_at: datetime
    is_favorited: bool = False

    model_config = {"from_attributes": True}
