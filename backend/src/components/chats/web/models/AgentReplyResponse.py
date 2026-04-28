from typing import Any, Dict
from pydantic import BaseModel


class AgentReplyResponse(BaseModel):
    reply: str
    chat_id: int
    chat_title: str
    metadata: Dict[str, Any] = {}
