from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    exp: Optional[datetime] = None
