from abc import ABC, abstractmethod
from typing import List
from src.components.chats.infrastructure.models.ChatMessageModel import ChatMessage


class IGetRecentMessagesQuery(ABC):
    @abstractmethod
    async def __call__(self, chat_id: int, limit: int = 20) -> List[ChatMessage]:
        ...
