from abc import ABC, abstractmethod


class IUpdateFavoriteCommand(ABC):
    @abstractmethod
    async def __call__(self, user_id: int, chat_id: int, custom_name: str) -> bool:
        ...
