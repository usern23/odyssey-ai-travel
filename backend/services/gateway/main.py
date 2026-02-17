from __future__ import annotations
from contextlib import asynccontextmanager
from typing import AsyncIterator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.common.configs import settings
from src.infrastructure.db.session import init_models
from src.components.users.infrastructure import models as user_models
from src.components.trips.infrastructure import models as trip_models
from src.components.agent.infrastructure import models as agent_models
from src.components.chats.infrastructure import models as chat_models
from src.components.favorites.infrastructure import models as favorite_models
from src.components.users.web import get_router as get_users_router
from src.components.trips.web import get_router as get_trips_router
from src.components.chats.web.views.chat_api import router as chats_router
from src.components.favorites.web.views.favorites_api import router as favorites_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await init_models()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=['*'],
            allow_headers=['*'])
    api_prefix = settings.api_v1_prefix
    app.include_router(get_users_router(), prefix=api_prefix)
    app.include_router(get_trips_router(), prefix=api_prefix)
    app.include_router(chats_router, prefix=api_prefix)
    app.include_router(favorites_router, prefix=api_prefix)

    @app.get('/', tags=['system'])
    async def root() -> dict[str, str]:
        return {'status': 'ok', 'message': settings.app_name}

    @app.get('/health', tags=['system'])
    async def health() -> dict[str, str]:
        return {'status': 'healthy'}
    return app


app = create_app()
