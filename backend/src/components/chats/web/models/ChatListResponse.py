from typing import List
from pydantic import BaseModel
from src.components.chats.web.models.ChatResponse import ChatResponse


class ChatListResponse(BaseModel):
    chats: List[ChatResponse]
    total: int
