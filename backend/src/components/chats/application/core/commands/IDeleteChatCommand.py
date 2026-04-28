from abc import ABC, abstractmethod


class IDeleteChatCommand(ABC):
    @abstractmethod
    async def __call__(self, chat_id: int, user_id: int) -> bool:
        ...
