from abc import ABC, abstractmethod
from typing import Optional
from src.components.favorites.infrastructure.models.FavoriteModel import Favorite


class IAddToFavoritesCommand(ABC):
    @abstractmethod
    async def __call__(self, user_id: int, trip_id: int, custom_name: Optional[str] = None) -> Favorite:
        ...
