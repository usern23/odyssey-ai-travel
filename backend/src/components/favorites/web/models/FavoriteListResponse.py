from __future__ import annotations
from typing import List
from pydantic import BaseModel
from src.components.favorites.web.models.FavoriteResponse import FavoriteResponse


class FavoriteListResponse(BaseModel):
    favorites: List[FavoriteResponse]
    total: int
