from __future__ import annotations
import logging
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from src.common.web.dependencies import get_current_user
from src.components.chats.application.core.queries import IGetChatWithMessagesQuery
from src.components.users.infrastructure.models import User

logger = logging.getLogger(__name__)

_NO_CACHE_HEADERS = {
    'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
    'Pragma': 'no-cache',
    'Expires': '0',
}


class GetRouteMapView:
    @inject
    async def __call__(
            self,
            chat_id: int,
            get_chat_with_messages: FromDishka[IGetChatWithMessagesQuery],
            refresh: int = Query(0, description='1 — пересобрать, игнорируя кэш'),
            current_user: User = Depends(get_current_user)):
        from src.components.agent.infrastructure.tools.auxiliary.RouteMapGenerator import (
            generate_route_map, invalidate_map_cache,
        )
        from src.components.travel_plan.domain.TravelPlanEntities import TravelPlan
        # Регенерируем HTML на каждый запрос — генерация быстрая (<50мс),
        # а in-memory кэш провоцирует «залипание» старой версии карты.
        invalidate_map_cache(chat_id)
        chat = await get_chat_with_messages(chat_id, current_user.id)
        if not chat:
            raise HTTPException(status_code=404, detail='Chat not found')
        trip = getattr(chat, 'trip', None)
        if not trip or not trip.generated_plan:
            raise HTTPException(status_code=404, detail='No travel plan found')
        try:
            plan = TravelPlan.from_dict(trip.generated_plan)
            html = generate_route_map(plan)
            return HTMLResponse(content=html, headers=_NO_CACHE_HEADERS)
        except Exception as e:
            logger.error('Failed to generate route map for chat %s: %s', chat_id, e)
            raise HTTPException(status_code=500, detail='Failed to generate map')
