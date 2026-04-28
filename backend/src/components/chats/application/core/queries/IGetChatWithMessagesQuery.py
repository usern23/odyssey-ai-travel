from abc import ABC, abstractmethod
from typing import Optional
from src.components.chats.infrastructure.models.ChatModel import Chat


class IGetChatWithMessagesQuery(ABC):
    @abstractmethod
    async def __call__(self, chat_id: int, user_id: int) -> Optional[Chat]:
        ...
