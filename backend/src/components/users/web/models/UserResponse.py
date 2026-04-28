from datetime import datetime
from pydantic import BaseModel, EmailStr


class UserResponse(BaseModel):
    model_config = {'from_attributes': True}

    id: int
    email: EmailStr
    timezone: str
    created_at: datetime
