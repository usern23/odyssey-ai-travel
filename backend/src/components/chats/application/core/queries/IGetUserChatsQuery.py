from abc import ABC, abstractmethod
from typing import List
from src.components.chats.infrastructure.models.ChatModel import Chat


class IGetUserChatsQuery(ABC):
    @abstractmethod
    async def __call__(self, user_id: int, limit: int = 50) -> List[Chat]:
        ...
