"""Q&A evaluation harness — test responses against ground truth."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def load_ground_truth(path: str) -> list[dict]:
    """Load ground truth Q&A pairs from a JSONL file.

    Each line: {"question": "...", "expected_answer": "...", "skill": "..."}
    """
    records = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def score_response(expected: str, actual: str) -> dict:
    """Score a response against an expected answer.

    Returns keyword_overlap (0-1 ratio) and exact_match (bool).
    """
    expected_words = set(expected.lower().split())
    actual_words = set(actual.lower().split())

    if not expected_words:
        return {"keyword_overlap": 0.0, "exact_match": actual.strip() == ""}

    overlap = len(expected_words & actual_words)
    ratio = overlap / len(expected_words)

    return {
        "keyword_overlap": round(ratio, 3),
        "exact_match": expected.strip().lower() == actual.strip().lower(),
    }


def run_eval(
    ground_truth: list[dict],
    api_caller: Callable[[str], str],
) -> dict:
    """Run eval over all ground truth pairs using the provided API caller.

    api_caller: takes a question string, returns a response string.
    Returns aggregate stats.
    """
    total = len(ground_truth)
    if total == 0:
        return {"total": 0, "mean_keyword_score": 0.0, "exact_matches": 0, "per_skill": {}}

    scores = []
    exact_matches = 0
    per_skill: dict[str, list[float]] = {}

    for item in ground_truth:
        question = item["question"]
        expected = item["expected_answer"]
        skill = item.get("skill", "unknown")

        actual = api_caller(question)
        result = score_response(expected, actual)

        scores.append(result["keyword_overlap"])
        if result["exact_match"]:
            exact_matches += 1

        per_skill.setdefault(skill, []).append(result["keyword_overlap"])

    mean_score = sum(scores) / len(scores) if scores else 0.0

    skill_averages = {
        skill: round(sum(vals) / len(vals), 3)
        for skill, vals in per_skill.items()
    }

    return {
        "total": total,
        "mean_keyword_score": round(mean_score, 3),
        "exact_matches": exact_matches,
        "per_skill": skill_averages,
    }


def evaluate(ground_truth_path: str, api_url: str):
    """Run evaluation suite against the Central API."""
    import httpx

    logger.info("Running eval against %s", api_url)

    ground_truth = load_ground_truth(ground_truth_path)

    def api_caller(question: str) -> str:
        resp = httpx.post(
            f"{api_url}/v1/message",
            json={
                "content": {"text": question},
                "user_identity": {"channel": "cli", "channel_user_id": "eval"},
                "context": {"conversation_id": "eval", "project": {}},
                "session": {"prior_messages": 0},
            },
            timeout=30.0,
        )
        data = resp.json()
        return data.get("text", "")

    results = run_eval(ground_truth, api_caller)
    logger.info("Eval results: %s", json.dumps(results, indent=2))
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--ground-truth", required=True)
    parser.add_argument("--api-url", default="http://localhost:8000")
    args = parser.parse_args()
    evaluate(args.ground_truth, args.api_url)
