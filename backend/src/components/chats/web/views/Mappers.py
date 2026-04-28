from src.components.chats.web.models.ChatResponse import ChatResponse
from src.components.chats.web.models.ChatMessageResponse import ChatMessageResponse
from src.components.chats.web.models.TripSummaryResponse import TripSummaryResponse


def trip_summary(trip) -> TripSummaryResponse | None:
    if not trip:
        return None
    return TripSummaryResponse(
        id=trip.id,
        name=trip.name,
        destination=trip.destination,
        origin=trip.origin,
        start_date=trip.start_date,
        end_date=trip.end_date,
        budget=trip.trip_profile.get('budget') if trip.trip_profile else None,
        has_plan=bool(trip.generated_plan))


def chat_to_response(chat, is_favorited: bool = False) -> ChatResponse:
    return ChatResponse(
        id=chat.id,
        title=chat.title,
        status=chat.status.value,
        trip_id=chat.trip_id,
        trip=trip_summary(getattr(chat, 'trip', None)),
        created_at=chat.created_at,
        updated_at=chat.updated_at,
        is_favorited=is_favorited)


def message_to_response(msg) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=msg.id,
        role=msg.role.value,
        content=msg.content,
        tool_name=msg.tool_name,
        created_at=msg.created_at)
