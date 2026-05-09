from abc import ABC, abstractmethod


class IUpdateFavoriteCommand(ABC):
    @abstractmethod
    async def __call__(self, user_id: int, trip_id: int, custom_name: str) -> bool:
        ...
