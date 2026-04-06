from __future__ import annotations
from typing import Optional
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from src.infrastructure.auth import get_password_hash, verify_password
from src.components.users.web.models.dto import UserCreate, UserProfileCreate, UserProfileUpdate
from src.components.users.infrastructure.models import User, UserProfile
from src.components.users.infrastructure.repositories import UserRepository, get_user_repository


class UserAlreadyExistsError(Exception):
    pass


class UserService:

    def __init__(
            self,
            session: AsyncSession,
            repository: Optional[UserRepository] = None):
        self.session = session
        self.repository = repository or get_user_repository(session)

    async def create_user(self, payload: UserCreate) -> User:
        user = User(
            email=payload.email,
            hashed_password=get_password_hash(
                payload.password),
            timezone=payload.timezone)
        self.session.add(user)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise UserAlreadyExistsError from exc
        await self.session.refresh(user)
        return user

    async def authenticate(self, email: str, password: str) -> Optional[User]:
        user = await self.repository.get_by_email(email)
        if not user:
            return None
        if not user.hashed_password:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    async def get_or_create_yandex_user(
            self, yandex_id: str, email: str) -> User:
        user = await self.repository.get_by_yandex_id(yandex_id)
        if user:
            return user
        existing = await self.repository.get_by_email(email)
        if existing:
            existing.yandex_id = yandex_id
            await self.session.commit()
            await self.session.refresh(existing)
            return existing
        user = User(email=email, yandex_id=yandex_id)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_profile(self, user_id: int) -> Optional[UserProfile]:
        return await self.repository.get_profile(user_id)

    async def create_profile(
            self,
            user_id: int,
            payload: UserProfileCreate) -> UserProfile:
        profile = UserProfile(
            user_id=user_id,
            activity_level=payload.activity_level,
            budget_level=payload.budget_level,
            category_preferences=payload.category_preferences,
            landscape_preferences=payload.landscape_preferences,
            food_preferences=payload.food_preferences,
            accommodation_preference=payload.accommodation_preference)
        await self.repository.add_profile(profile)
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def update_profile(
            self,
            user_id: int,
            payload: UserProfileUpdate) -> Optional[UserProfile]:
        profile = await self.get_profile(user_id)
        if not profile:
            return None
        for field, value in payload.dict(exclude_unset=True).items():
            setattr(profile, field, value)
        await self.session.commit()
        await self.session.refresh(profile)
        return profile
