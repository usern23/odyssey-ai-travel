from __future__ import annotations
from contextlib import asynccontextmanager
from typing import AsyncIterator
from dishka import make_async_container
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.common.configs import settings
from src.infrastructure.db.session import init_models
from src.infrastructure.db.DatabaseProvider import DatabaseProvider
from src.components.users.infrastructure import models as user_models
from src.components.trips.infrastructure import models as trip_models
from src.components.agent.infrastructure import models as agent_models
from src.components.chats.infrastructure import models as chat_models
from src.components.favorites.infrastructure.models import Favorite as _favorite_model
from src.components.trips.application.TripsApplication import TripsApplication
from src.components.trips.web.TripsWebRouter import TripsWebRouter
from src.components.users.application.UsersApplication import UsersApplication
from src.components.users.web.UsersWebRouter import UsersWebRouter
from src.components.chats.application.ChatsApplication import ChatsApplication
from src.components.chats.web.ChatsWebRouter import ChatsWebRouter
from src.components.favorites.application.FavoritesApplication import FavoritesApplication
from src.components.favorites.web.FavoritesWebRouter import FavoritesWebRouter
from src.components.agent.application.AgentApplication import AgentApplication
from src.components.agent.web.AgentWebRouter import AgentWebRouter


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_models()
    yield
    await app.state.dishka_container.close()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=['*'],
            allow_headers=['*'])

    container = make_async_container(
        DatabaseProvider(),
        UsersApplication()(),
        ChatsApplication()(),
        FavoritesApplication()(),
        TripsApplication()(),
        AgentApplication()(),
    )
    setup_dishka(container, app)

    api_prefix = settings.api_v1_prefix
    UsersWebRouter()(app, prefix=api_prefix)
    TripsWebRouter()(app, prefix=api_prefix)
    ChatsWebRouter()(app, prefix=api_prefix)
    FavoritesWebRouter()(app, prefix=api_prefix)
    AgentWebRouter()(app, prefix=api_prefix)

    @app.get('/', tags=['system'])
    async def root() -> dict[str, str]:
        return {'status': 'ok', 'message': settings.app_name}

    @app.get('/health', tags=['system'])
    async def health() -> dict[str, str]:
        return {'status': 'healthy'}
    return app


app = create_app()
