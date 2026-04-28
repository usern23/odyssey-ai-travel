from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class FavoriteResponse(BaseModel):
    id: int
    chat_id: int
    chat_title: str
    custom_name: Optional[str] = None
    destination: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
