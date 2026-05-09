from abc import ABC, abstractmethod


class IRemoveFromFavoritesCommand(ABC):
    @abstractmethod
    async def __call__(self, user_id: int, trip_id: int) -> bool:
        ...
