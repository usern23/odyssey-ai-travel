from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class FavoriteCreateRequest(BaseModel):
    chat_id: int
    custom_name: Optional[str] = Field(None, max_length=255)
