from abc import ABC, abstractmethod


class ILinkTripToChatCommand(ABC):
    @abstractmethod
    async def __call__(self, chat_id: int, trip_id: int) -> None:
        ...
