from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    tool_name: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
