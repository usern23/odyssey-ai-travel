from abc import ABC, abstractmethod


class IIsFavoritedQuery(ABC):
    @abstractmethod
    async def __call__(self, user_id: int, chat_id: int) -> bool:
        ...
