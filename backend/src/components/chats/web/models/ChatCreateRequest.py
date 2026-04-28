from typing import Optional
from pydantic import BaseModel, Field


class ChatCreateRequest(BaseModel):
    message: Optional[str] = Field(
        None, description='Optional first message to send')
