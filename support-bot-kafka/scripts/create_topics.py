"""Idempotent Kafka topic creation script.

Usage:
    python -m support-bot-kafka.scripts.create_topics [--bootstrap localhost:9092]
"""

from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_topics(bootstrap_servers: str = "localhost:9092") -> None:
    """Create all FloxBot Kafka topics idempotently."""
    from kafka.admin import KafkaAdminClient, NewTopic
    from kafka.errors import TopicAlreadyExistsError

    from config.topics import TOPIC_CONFIGS

    admin = KafkaAdminClient(bootstrap_servers=bootstrap_servers)

    existing = set(admin.list_topics())

    for tc in TOPIC_CONFIGS:
        if tc.name in existing:
            logger.info("Topic %s already exists, skipping", tc.name)
            continue

        topic = NewTopic(
            name=tc.name,
            num_partitions=tc.partitions,
            replication_factor=1,
            topic_configs=(
                {"retention.ms": str(tc.retention_ms)} if tc.retention_ms > 0 else {}
            ),
        )
        try:
            admin.create_topics([topic])
            logger.info("Created topic %s (%d partitions)", tc.name, tc.partitions)
        except TopicAlreadyExistsError:
            logger.info("Topic %s created concurrently, skipping", tc.name)

    admin.close()
    logger.info("All topics verified.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create FloxBot Kafka topics")
    parser.add_argument("--bootstrap", default="localhost:9092")
    args = parser.parse_args()
    create_topics(args.bootstrap)
