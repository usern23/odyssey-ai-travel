from __future__ import annotations
import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional, Type
import aio_pika
from aio_pika import ExchangeType, Message, DeliveryMode
from aio_pika.abc import AbstractChannel, AbstractConnection, AbstractExchange, AbstractQueue
from src.common.configs.settings import settings
from src.common.events.types import Event, event_from_dict
logger = logging.getLogger(__name__)
EXCHANGE_NAME = 'odyssey.events'
QUEUE_TRIP_PROCESSOR = 'odyssey.trip.processor'
QUEUE_CHAT_PROCESSOR = 'odyssey.chat.processor'
QUEUE_FAVORITES_PROCESSOR = 'odyssey.favorites.processor'
ROUTING_KEY_TRIP_DATA_COLLECTED = 'trip.data.collected'
ROUTING_KEY_TRIP_PLAN_GENERATED = 'trip.plan.generated'
ROUTING_KEY_CHAT_MESSAGE_SAVED = 'chat.message.saved'
ROUTING_KEY_CHAT_TITLE_UPDATED = 'chat.title.updated'
ROUTING_KEY_CHAT_CONTEXT_UPDATED = 'chat.context.updated'
ROUTING_KEY_FAVORITES_ADDED = 'favorites.added'
ROUTING_KEY_FAVORITES_REMOVED = 'favorites.removed'


def get_routing_key_for_event(event: Event) -> str:
    mapping = {
        'TripDataCollectedEvent': ROUTING_KEY_TRIP_DATA_COLLECTED,
        'TravelPlanGeneratedEvent': ROUTING_KEY_TRIP_PLAN_GENERATED,
        'MessageSavedEvent': ROUTING_KEY_CHAT_MESSAGE_SAVED,
        'ChatTitleUpdateEvent': ROUTING_KEY_CHAT_TITLE_UPDATED,
        'ChatContextUpdateEvent': ROUTING_KEY_CHAT_CONTEXT_UPDATED,
        'AddToFavoritesEvent': ROUTING_KEY_FAVORITES_ADDED,
        'RemoveFromFavoritesEvent': ROUTING_KEY_FAVORITES_REMOVED}
    return mapping.get(event.event_type, 'unknown')


class RabbitMQPublisher:

    def __init__(self, rabbitmq_url: Optional[str] = None):
        self.rabbitmq_url = rabbitmq_url or settings.rabbitmq_url
        self._connection: Optional[AbstractConnection] = None
        self._channel: Optional[AbstractChannel] = None
        self._exchange: Optional[AbstractExchange] = None

    async def connect(self) -> None:
        if self._connection is None or self._connection.is_closed:
            self._connection = await aio_pika.connect_robust(self.rabbitmq_url)
            self._channel = await self._connection.channel()
            self._exchange = await self._channel.declare_exchange(EXCHANGE_NAME, ExchangeType.TOPIC, durable=True)
            logger.info(f'Connected to RabbitMQ, exchange: {EXCHANGE_NAME}')

    async def close(self) -> None:
        if self._connection and (not self._connection.is_closed):
            await self._connection.close()
            logger.info('RabbitMQ connection closed')

    async def __aenter__(self) -> 'RabbitMQPublisher':
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def publish(self, event: Event) -> None:
        if not self._exchange:
            await self.connect()
        routing_key = get_routing_key_for_event(event)
        message = Message(
            body=event.to_json().encode('utf-8'),
            content_type='application/json',
            delivery_mode=DeliveryMode.PERSISTENT,
            headers={
                'event_type': event.event_type,
                'event_id': event.event_id})
        await self._exchange.publish(message, routing_key=routing_key)
        logger.debug(
            f"Published {
                event.event_type} with routing key '{routing_key}', event_id={
                event.event_id}")


_publisher: Optional[RabbitMQPublisher] = None


async def get_publisher() -> RabbitMQPublisher:
    global _publisher
    if _publisher is None:
        _publisher = RabbitMQPublisher()
        await _publisher.connect()
    return _publisher


async def publish_event(event: Event) -> None:
    publisher = await get_publisher()
    await publisher.publish(event)


class RabbitMQConsumer(ABC):
    queue_name: str = ''
    routing_keys: list[str] = []
    prefetch_count: int = 10

    def __init__(self, rabbitmq_url: Optional[str] = None):
        self.rabbitmq_url = rabbitmq_url or settings.rabbitmq_url
        self._connection: Optional[AbstractConnection] = None
        self._channel: Optional[AbstractChannel] = None
        self._queue: Optional[AbstractQueue] = None
        self._running = False

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(self.rabbitmq_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=self.prefetch_count)
        exchange = await self._channel.declare_exchange(EXCHANGE_NAME, ExchangeType.TOPIC, durable=True)
        self._queue = await self._channel.declare_queue(self.queue_name, durable=True, arguments={'x-dead-letter-exchange': f'{EXCHANGE_NAME}.dlx', 'x-dead-letter-routing-key': f'{self.queue_name}.dead'})
        for routing_key in self.routing_keys:
            await self._queue.bind(exchange, routing_key=routing_key)

    async def close(self) -> None:
        if self._connection and (not self._connection.is_closed):
            await self._connection.close()

    @abstractmethod
    async def process_event(self, event: Event) -> None:
        pass

    async def _handle_message(self, message: aio_pika.IncomingMessage) -> None:
        async with message.process(requeue=False):
            try:
                data = json.loads(message.body.decode('utf-8'))
                event = event_from_dict(data)
                await self.process_event(event)
            except Exception as e:
                logger.error(f'Error processing message: {e}', exc_info=True)
                raise

    async def run(self) -> None:
        await self.connect()
        self._running = True
        logger.info(f'Consumer {self.queue_name} started')
        await self._queue.consume(self._handle_message)
        while self._running:
            await asyncio.sleep(1)
        await self.close()
        logger.info(f'Consumer {self.queue_name} stopped')

    def stop(self) -> None:
        self._running = False
