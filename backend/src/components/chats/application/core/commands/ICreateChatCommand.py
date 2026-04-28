from abc import ABC, abstractmethod
from src.components.chats.infrastructure.models.ChatModel import Chat


class ICreateChatCommand(ABC):
    @abstractmethod
    async def __call__(self, user_id: int) -> Chat:
        ...
