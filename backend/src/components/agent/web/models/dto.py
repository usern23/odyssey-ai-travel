from __future__ import annotations
from typing import Any, Dict, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class AgentChatRequest(BaseModel):
    chat_id: Optional[int] = None
    message: str = Field(..., min_length=1)


class AgentChatResponse(BaseModel):
    reply: str
    chat_id: int
    metadata: Dict[str, Any] = Field(default_factory=dict)
