from __future__ import annotations
from fastapi import APIRouter


def get_router() -> APIRouter:
    from .views.api import router as trips_router
    router = APIRouter()
    router.include_router(trips_router)
    return router
