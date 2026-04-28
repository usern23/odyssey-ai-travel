from typing import Optional
from pydantic import BaseModel, Field


class ChatUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
