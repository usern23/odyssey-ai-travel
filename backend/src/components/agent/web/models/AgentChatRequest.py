from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AgentChatRequest(BaseModel):
    chat_id: Optional[int] = None
    message: str = Field(..., min_length=1)
