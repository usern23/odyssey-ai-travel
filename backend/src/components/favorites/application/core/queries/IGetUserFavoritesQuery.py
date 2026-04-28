from abc import ABC, abstractmethod
from typing import List
from src.components.favorites.infrastructure.models.FavoriteModel import Favorite


class IGetUserFavoritesQuery(ABC):
    @abstractmethod
    async def __call__(self, user_id: int) -> List[Favorite]:
        ...
