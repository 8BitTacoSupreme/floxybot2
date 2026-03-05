"""Q&A evaluation harness — test responses against ground truth."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def evaluate(ground_truth_path: str, api_url: str):
    """Run evaluation suite against the Central API.

    TODO: Implement:
    1. Load ground truth Q&A pairs
    2. Send each question to the API
    3. Compare responses (semantic similarity + exact match)
    4. Report accuracy, latency, confidence distribution
    """
    logger.info("Running eval against %s", api_url)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--ground-truth", required=True)
    parser.add_argument("--api-url", default="http://localhost:8000")
    args = parser.parse_args()
    evaluate(args.ground_truth, args.api_url)
