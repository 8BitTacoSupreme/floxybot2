"""CLI entry point for streaming consumers.

Usage:
    python -m support-bot-flink.runner vote-agg
    python -m support-bot-flink.runner xc-correlation
    python -m support-bot-flink.runner canon-gaps
    python -m support-bot-flink.runner trending
    python -m support-bot-flink.runner feedback-router
    python -m support-bot-flink.runner all
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CONSUMERS = {
    "vote-agg": "jobs.vote_aggregation:VoteAggregationConsumer",
    "xc-correlation": "jobs.cross_channel_correlation:CrossChannelConsumer",
    "canon-gaps": "jobs.canon_gap_detection:CanonGapConsumer",
    "trending": "jobs.trending_issues:TrendingIssuesConsumer",
    "feedback-router": "jobs.feedback_router:FeedbackRouterConsumer",
    "telemetry": "jobs.telemetry_consumer:TelemetryConsumer",
}


def _load_consumer(name: str):
    """Import and instantiate a consumer by name."""
    module_path, class_name = CONSUMERS[name].rsplit(":", 1)
    import importlib
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls()


async def run_consumer(name: str, bootstrap: str) -> None:
    """Run a single consumer."""
    consumer = _load_consumer(name)
    logger.info("Starting consumer: %s", name)
    await consumer.run_kafka_loop(bootstrap)


async def run_all(bootstrap: str) -> None:
    """Run all consumers concurrently."""
    tasks = [run_consumer(name, bootstrap) for name in CONSUMERS]
    await asyncio.gather(*tasks)


def main() -> None:
    parser = argparse.ArgumentParser(description="FloxBot streaming consumers")
    parser.add_argument("consumer", choices=list(CONSUMERS.keys()) + ["all"])
    parser.add_argument("--bootstrap", default="localhost:9092")
    args = parser.parse_args()

    if args.consumer == "all":
        asyncio.run(run_all(args.bootstrap))
    else:
        asyncio.run(run_consumer(args.consumer, args.bootstrap))


if __name__ == "__main__":
    main()
