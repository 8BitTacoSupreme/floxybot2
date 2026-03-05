"""Event publisher protocol and implementations."""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class EventPublisher(Protocol):
    """Protocol for event publishers."""

    async def publish(self, topic: str, key: str, value: dict[str, Any]) -> None: ...
    async def close(self) -> None: ...


class InMemoryPublisher:
    """In-memory event store for testing."""

    def __init__(self):
        self.events: list[dict[str, Any]] = []

    async def publish(self, topic: str, key: str, value: dict[str, Any]) -> None:
        self.events.append({"topic": topic, "key": key, "value": value})

    async def close(self) -> None:
        pass

    def get_events(self, topic: str | None = None) -> list[dict[str, Any]]:
        if topic is None:
            return list(self.events)
        return [e for e in self.events if e["topic"] == topic]


class KafkaPublisher:
    """Kafka event publisher using aiokafka."""

    def __init__(self, bootstrap_servers: str | None = None):
        if bootstrap_servers is None:
            from src.config import settings
            bootstrap_servers = settings.KAFKA_BOOTSTRAP
        self._bootstrap_servers = bootstrap_servers
        self._producer = None

    async def _ensure_producer(self):
        if self._producer is None:
            from aiokafka import AIOKafkaProducer
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap_servers,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
            )
            await self._producer.start()

    async def publish(self, topic: str, key: str, value: dict[str, Any]) -> None:
        await self._ensure_producer()
        await self._producer.send_and_wait(topic, value=value, key=key)
        logger.info("Published event to %s (key=%s)", topic, key)

    async def close(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None
