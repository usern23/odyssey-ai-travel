from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.components.users.application.core.queries.IAuthenticateUserQuery import IAuthenticateUserQuery
from src.components.users.infrastructure.models.UserModel import User
from src.infrastructure.auth import verify_password


class AuthenticateUserQuery(IAuthenticateUserQuery):

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def __call__(self, email: str, password: str) -> Optional[User]:
        result = await self.db_session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user or not user.hashed_password:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user
