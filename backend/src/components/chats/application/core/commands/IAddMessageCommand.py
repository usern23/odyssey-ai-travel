from abc import ABC, abstractmethod
from typing import Optional
from src.components.chats.infrastructure.models.ChatMessageModel import ChatMessage, MessageRole


class IAddMessageCommand(ABC):
    @abstractmethod
    async def __call__(
            self,
            chat_id: int,
            role: MessageRole,
            content: str,
            tool_name: Optional[str] = None,
            tool_call_id: Optional[str] = None) -> ChatMessage:
        ...
