"""Abstract base for streaming consumers.

Provides the consumer loop structure and event processing contract.
Concrete consumers implement ``process_event()`` and ``emit_window()``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class StreamConsumer(ABC):
    """Base class for streaming event consumers.

    Subclasses must implement:
    - process_event(event): handle a single event, return any outputs
    - flush(): force-close all windows and return final outputs
    """

    def __init__(self, topics: list[str], group_id: str):
        self.topics = topics
        self.group_id = group_id
        self._running = False
        self._outputs: list[dict[str, Any]] = []

    @abstractmethod
    def process_event(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        """Process a single event. Return any outputs to emit."""
        ...

    @abstractmethod
    def flush(self) -> list[dict[str, Any]]:
        """Force-close all windows and return final outputs."""
        ...

    def get_outputs(self) -> list[dict[str, Any]]:
        """Return all accumulated outputs."""
        return list(self._outputs)

    def clear_outputs(self) -> None:
        """Clear accumulated outputs."""
        self._outputs.clear()

    async def run_on_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Process a batch of events (for testing without Kafka)."""
        all_outputs = []
        for event in events:
            outputs = self.process_event(event)
            all_outputs.extend(outputs)
            self._outputs.extend(outputs)

        # Flush remaining windows
        final = self.flush()
        all_outputs.extend(final)
        self._outputs.extend(final)

        return all_outputs

    async def run_kafka_loop(self, bootstrap_servers: str = "localhost:9092") -> None:
        """Run the consumer loop against a real Kafka cluster."""
        from aiokafka import AIOKafkaConsumer

        consumer = AIOKafkaConsumer(
            *self.topics,
            bootstrap_servers=bootstrap_servers,
            group_id=self.group_id,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            auto_offset_reset="earliest",
        )
        await consumer.start()
        self._running = True
        logger.info("Consumer %s started on topics %s", self.group_id, self.topics)

        try:
            async for msg in consumer:
                if not self._running:
                    break
                outputs = self.process_event(msg.value)
                self._outputs.extend(outputs)
                for out in outputs:
                    logger.info("[%s] output: %s", self.group_id, out)
        finally:
            await consumer.stop()

    def stop(self) -> None:
        """Signal the consumer loop to stop."""
        self._running = False
