from abc import ABC, abstractmethod


class IUpdateChatTitleCommand(ABC):
    @abstractmethod
    async def __call__(self, chat_id: int, title: str) -> None:
        ...
