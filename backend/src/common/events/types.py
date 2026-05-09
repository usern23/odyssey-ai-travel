from __future__ import annotations
import json
from abc import ABC
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4


@dataclass
class Event(ABC):
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def event_type(self) -> str:
        return self.__class__.__name__

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['event_type'] = self.event_type
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class ChatCreatedEvent(Event):
    user_id: int = 0
    chat_id: int = 0


@dataclass
class ChatTitleUpdateEvent(Event):
    chat_id: int = 0
    title: str = ''


@dataclass
class ChatContextUpdateEvent(Event):
    chat_id: int = 0
    travel_context: Optional[Dict[str, Any]] = None


@dataclass
class MessageSavedEvent(Event):
    chat_id: int = 0
    role: str = ''
    content: str = ''
    metadata: Optional[Dict[str, Any]] = None
    tool_name: Optional[str] = None
    tool_call_id: Optional[str] = None


@dataclass
class AddToFavoritesEvent(Event):
    user_id: int = 0
    trip_id: int = 0
    custom_name: Optional[str] = None


@dataclass
class RemoveFromFavoritesEvent(Event):
    user_id: int = 0
    trip_id: int = 0


@dataclass
class AgentProcessingStartedEvent(Event):
    chat_id: int = 0
    user_id: int = 0
    message: str = ''


@dataclass
class AgentProcessingCompletedEvent(Event):
    chat_id: int = 0
    user_id: int = 0
    reply: str = ''
    tool_calls: Optional[str] = None
    generated_plan: Optional[str] = None


@dataclass
class ToolExecutedEvent(Event):
    chat_id: int = 0
    tool_name: str = ''
    tool_input: str = ''
    tool_output: str = ''
    execution_time_ms: int = 0


@dataclass
class TripDataCollectedEvent(Event):
    chat_id: int = 0
    user_id: int = 0
    destination: str = ''
    start_date: str = ''
    end_date: str = ''
    budget: str = ''
    origin: Optional[str] = None
    travelers_count: int = 1
    travel_style: Optional[str] = None
    interests: Optional[str] = None
    special_requirements: Optional[str] = None


@dataclass
class TravelPlanGeneratedEvent(Event):
    chat_id: int = 0
    user_id: int = 0
    trip_id: int = 0
    destination: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    plan_data: str = ''


@dataclass
class TripDataMissingEvent(Event):
    chat_id: int = 0
    user_id: int = 0
    missing_fields: str = ''
    collected_so_far: str = ''


EVENT_TYPES: Dict[str,
                  type] = {'ChatCreatedEvent': ChatCreatedEvent,
                           'ChatTitleUpdateEvent': ChatTitleUpdateEvent,
                           'ChatContextUpdateEvent': ChatContextUpdateEvent,
                           'MessageSavedEvent': MessageSavedEvent,
                           'AddToFavoritesEvent': AddToFavoritesEvent,
                           'RemoveFromFavoritesEvent': RemoveFromFavoritesEvent,
                           'AgentProcessingStartedEvent': AgentProcessingStartedEvent,
                           'AgentProcessingCompletedEvent': AgentProcessingCompletedEvent,
                           'ToolExecutedEvent': ToolExecutedEvent,
                           'TripDataCollectedEvent': TripDataCollectedEvent,
                           'TravelPlanGeneratedEvent': TravelPlanGeneratedEvent,
                           'TripDataMissingEvent': TripDataMissingEvent}


def event_from_dict(data: Dict[str, Any]) -> Event:
    event_type = data.pop('event_type', None)
    if not event_type or event_type not in EVENT_TYPES:
        raise ValueError(f'Unknown event type: {event_type}')
    event_class = EVENT_TYPES[event_type]
    return event_class(**data)


def event_from_json(json_str: str) -> Event:
    data = json.loads(json_str)
    return event_from_dict(data)
