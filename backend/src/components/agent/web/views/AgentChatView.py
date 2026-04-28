from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections import defaultdict
from typing import Dict, Optional, Tuple

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import Depends, Header, HTTPException, status

from src.common.web.dependencies import get_current_user
from src.components.agent.application.AgentHostService import AgentHostService
from src.components.agent.web.models.AgentChatRequest import AgentChatRequest
from src.components.agent.web.models.AgentChatResponse import AgentChatResponse
from src.components.chats.application.core.queries import IGetChatQuery
from src.components.chats.application.core.commands import ICreateChatCommand
from src.components.users.infrastructure.models import User

logger = logging.getLogger(__name__)

# In-memory idempotency cache.
# Key: (user_id, idempotency_key_or_content_hash) -> (expires_at, cached_response|None, processing_event)
# - If cached_response is not None, return it.
# - Otherwise await processing_event, then return the stored response.
_IDEMPOTENCY_TTL_SECONDS = 60.0
_idempotency_cache: Dict[
    Tuple[int, str], Tuple[float, Optional[AgentChatResponse], asyncio.Event]
] = {}
_idempotency_lock = asyncio.Lock()
# Per-chat serialization lock so two concurrent sends to the same chat do not
# race through the agent simultaneously (which would cause duplicate LLM calls).
_chat_locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def _content_hash(user_id: int, chat_id: Optional[int], message: str) -> str:
    raw = f'{user_id}:{chat_id or 0}:{message}'.encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


async def _gc_idempotency_cache() -> None:
    now = time.monotonic()
    async with _idempotency_lock:
        expired = [k for k, (exp, _, _) in _idempotency_cache.items() if exp < now]
        for k in expired:
            _idempotency_cache.pop(k, None)


class AgentChatView:

    @inject
    async def __call__(
        self,
        payload: AgentChatRequest,
        agent_service: FromDishka[AgentHostService],
        get_chat_query: FromDishka[IGetChatQuery],
        create_chat_command: FromDishka[ICreateChatCommand],
        current_user: User = Depends(get_current_user),
        idempotency_key: Optional[str] = Header(default=None, alias='Idempotency-Key'),
    ) -> AgentChatResponse:
        # Determine or create the chat first so idempotency keys can include chat_id.
        if payload.chat_id:
            chat = await get_chat_query.execute(payload.chat_id, current_user.id)
            if not chat:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail='Chat not found',
                )
        else:
            chat = await create_chat_command.execute(current_user.id)

        # Build idempotency cache key: explicit client key wins, otherwise fall back
        # to (user, chat, message) hash so fast duplicate submits still dedupe.
        cache_key_part = idempotency_key or _content_hash(
            current_user.id, chat.id, payload.message
        )
        cache_key = (current_user.id, cache_key_part)

        await _gc_idempotency_cache()

        async with _idempotency_lock:
            entry = _idempotency_cache.get(cache_key)
            if entry is not None:
                expires_at, cached_response, event = entry
                if expires_at >= time.monotonic():
                    if cached_response is not None:
                        logger.info(
                            'Idempotent replay for user=%s chat=%s', current_user.id, chat.id
                        )
                        return cached_response
                    # Request is in flight — wait for it to complete below.
                    in_flight_event = event
                else:
                    _idempotency_cache.pop(cache_key, None)
                    entry = None
                    in_flight_event = None
            else:
                in_flight_event = None

            if entry is None:
                in_flight_event = asyncio.Event()
                _idempotency_cache[cache_key] = (
                    time.monotonic() + _IDEMPOTENCY_TTL_SECONDS,
                    None,
                    in_flight_event,
                )
                owner = True
            else:
                owner = False

        if not owner:
            # Wait for the in-flight request to finish, then return its cached result.
            try:
                await asyncio.wait_for(in_flight_event.wait(), timeout=120.0)
            except asyncio.TimeoutError:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail='Duplicate request still in flight. Please retry.',
                )
            async with _idempotency_lock:
                entry = _idempotency_cache.get(cache_key)
            if entry and entry[1] is not None:
                return entry[1]
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='Duplicate request failed. Please retry.',
            )

        # Serialize per-chat message processing to avoid overlapping agent runs.
        chat_lock = _chat_locks[chat.id]
        try:
            async with chat_lock:
                response = await agent_service.process_message(
                    user_id=current_user.id,
                    chat_id=chat.id,
                    message=payload.message,
                )
            async with _idempotency_lock:
                _idempotency_cache[cache_key] = (
                    time.monotonic() + _IDEMPOTENCY_TTL_SECONDS,
                    response,
                    in_flight_event,
                )
            return response
        except Exception:
            async with _idempotency_lock:
                _idempotency_cache.pop(cache_key, None)
            raise
        finally:
            in_flight_event.set()
