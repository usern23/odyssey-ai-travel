from __future__ import annotations
from pydantic import BaseModel, Field


class FavoriteUpdateRequest(BaseModel):
    custom_name: str = Field(..., max_length=255)
