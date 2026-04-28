from __future__ import annotations
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from src.common.events.rabbitmq import publish_event
from src.common.events.types import TripDataCollectedEvent, TripDataMissingEvent
logger = logging.getLogger(__name__)
REQUIRED_FIELDS = ['destination', 'start_date', 'end_date', 'budget']


@dataclass
class CollectedTripData:
    destination: str
    start_date: str
    end_date: str
    budget: str
    origin: Optional[str] = None
    travelers_count: int = 1
    travel_style: Optional[str] = None
    interests: Optional[List[str]] = None
    special_requirements: Optional[Dict[str, Any]] = None


class TripDataCollector:

    async def collect_and_validate(self,
                                   chat_id: int,
                                   user_id: int,
                                   destination: Optional[str] = None,
                                   start_date: Optional[str] = None,
                                   end_date: Optional[str] = None,
                                   budget: Optional[str] = None,
                                   origin: Optional[str] = None,
                                   travelers_count: int = 1,
                                   travel_style: Optional[str] = None,
                                   interests: Optional[List[str]] = None,
                                   special_requirements: Optional[Dict[str,
                                                                       Any]] = None) -> Dict[str,
                                                                                             Any]:
        collected = {
            'destination': destination,
            'start_date': start_date,
            'end_date': end_date,
            'budget': budget}
        missing = [field for field, value in collected.items() if not value]
        if missing:
            await publish_event(TripDataMissingEvent(chat_id=chat_id, user_id=user_id, missing_fields=json.dumps(missing), collected_so_far=json.dumps({k: v for k, v in collected.items() if v})))
            return {
                'status': 'missing',
                'missing_fields': missing,
                'collected_so_far': {
                    k: v for k,
                    v in collected.items() if v},
                'message': self._get_missing_message(missing)}
        try:
            start = self._parse_date(start_date)
            end = self._parse_date(end_date)
            if end <= start:
                return {
                    'status': 'error',
                    'error': 'End date must be after start date'}
        except ValueError as e:
            return {'status': 'error', 'error': f'Invalid date format: {e}'}
        valid_budgets = ['economy', 'comfort', 'unlimited']
        if budget.lower() not in valid_budgets:
            return {
                'status': 'error',
                'error': f'Invalid budget. Must be one of: {valid_budgets}'}
        await publish_event(TripDataCollectedEvent(chat_id=chat_id, user_id=user_id, destination=destination, start_date=start.isoformat(), end_date=end.isoformat(), budget=budget.lower(), origin=origin, travelers_count=travelers_count, travel_style=travel_style, interests=json.dumps(interests) if interests else None, special_requirements=json.dumps(special_requirements) if special_requirements else None))
        logger.info(
            f'Published TripDataCollectedEvent for chat {chat_id}: {destination}, {start_date} - {end_date}, {budget}')
        return {
            'status': 'collected',
            'message': f'Данные о поездке собраны! Направление: {destination}, даты: {start_date} - {end_date}, бюджет: {budget}.',
            'trip_data': {
                'destination': destination,
                'start_date': start.isoformat(),
                'end_date': end.isoformat(),
                'budget': budget,
                'origin': origin,
                'travelers_count': travelers_count}}

    def _parse_date(self, date_str: str) -> date:
        formats = ['%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%Y/%m/%d']
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        raise ValueError(f'Cannot parse date: {date_str}')

    def _get_missing_message(self, missing: List[str]) -> str:
        field_names = {
            'destination': 'направление поездки',
            'start_date': 'дата начала',
            'end_date': 'дата окончания',
            'budget': 'бюджет'}
        missing_ru = [field_names.get(f, f) for f in missing]
        if len(missing_ru) == 1:
            return f'Пожалуйста, уточните {missing_ru[0]}.'
        else:
            return f"Пожалуйста, уточните: {', '.join(missing_ru)}."


_collector: Optional[TripDataCollector] = None


def get_trip_data_collector() -> TripDataCollector:
    global _collector
    if _collector is None:
        _collector = TripDataCollector()
    return _collector
