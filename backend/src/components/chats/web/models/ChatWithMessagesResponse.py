from typing import List
from pydantic import BaseModel
from src.components.chats.web.models.ChatMessageResponse import ChatMessageResponse
from src.components.chats.web.models.ChatResponse import ChatResponse


class ChatWithMessagesResponse(ChatResponse):
    messages: List[ChatMessageResponse] = []
