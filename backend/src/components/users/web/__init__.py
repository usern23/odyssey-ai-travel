from __future__ import annotations
from fastapi import APIRouter


def get_router() -> APIRouter:
    from .views.auth import router as auth_router
    from .views.profile import router as profile_router
    router = APIRouter()
    router.include_router(auth_router)
    router.include_router(profile_router)
    return router
