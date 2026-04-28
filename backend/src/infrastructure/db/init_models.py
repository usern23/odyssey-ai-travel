"""
Initialize all SQLAlchemy models to prevent circular import issues.
This module should be imported BEFORE creating any database sessions.
"""
from __future__ import annotations

# Import all models in correct order to register them with Base and prevent circular imports
# Order matters: users first (no dependencies), then trips, then chats (depends on both), etc.

from src.components.users.infrastructure.models.UserModel import User  # noqa: F401
from src.components.users.infrastructure.models.UserProfileModel import UserProfile  # noqa: F401
from src.components.trips.infrastructure.models.TripModel import Trip  # noqa: F401
from src.components.chats.infrastructure.models.ChatModel import Chat  # noqa: F401
from src.components.chats.infrastructure.models.ChatMessageModel import ChatMessage  # noqa: F401
from src.components.favorites.infrastructure.models.FavoriteModel import Favorite  # noqa: F401
from src.components.agent.infrastructure.models import AgentModel  # noqa: F401

__all__ = [
    'User',
    'UserProfile', 
    'Trip',
    'Chat',
    'ChatMessage',
    'Favorite',
    'AgentModel',
]
