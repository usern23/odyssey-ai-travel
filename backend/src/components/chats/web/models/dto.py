from __future__ import annotations
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatCreate(BaseModel):
    message: Optional[str] = Field(
        None, description='Optional first message to send')


class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)


class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    tool_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TripSummary(BaseModel):
    id: int
    name: str
    destination: Optional[str] = None
    origin: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    budget: Optional[str] = None
    has_plan: bool = False

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    id: int
    title: str
    status: str
    trip_id: Optional[int] = None
    trip: Optional[TripSummary] = None
    created_at: datetime
    updated_at: datetime
    is_favorited: bool = False

    class Config:
        from_attributes = True


class ChatWithMessagesResponse(ChatResponse):
    messages: List[ChatMessageResponse] = []


class ChatListResponse(BaseModel):
    chats: List[ChatResponse]
    total: int


class ChatUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=255)


class AgentReplyResponse(BaseModel):
    reply: str
    chat_id: int
    chat_title: str
    metadata: Dict[str, Any] = {}


class FavoriteCreate(BaseModel):
    chat_id: int
    custom_name: Optional[str] = Field(None, max_length=255)


class FavoriteUpdate(BaseModel):
    custom_name: str = Field(..., max_length=255)


class FavoriteResponse(BaseModel):
    id: int
    chat_id: int
    chat_title: str
    custom_name: Optional[str] = None
    destination: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class FavoriteListResponse(BaseModel):
    favorites: List[FavoriteResponse]
    total: int
