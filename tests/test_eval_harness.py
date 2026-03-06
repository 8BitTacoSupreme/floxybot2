"""Tests for the canon eval harness."""

from __future__ import annotations

import json
import tempfile

from scripts.eval_harness import load_ground_truth, run_eval, score_response


class TestLoadGroundTruth:
    def test_parse_jsonl(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"question": "Q1", "expected_answer": "A1", "skill": "core-canon"}) + "\n")
            f.write(json.dumps({"question": "Q2", "expected_answer": "A2", "skill": "k8s"}) + "\n")
            path = f.name

        records = load_ground_truth(path)
        assert len(records) == 2
        assert records[0]["question"] == "Q1"
        assert records[1]["skill"] == "k8s"


class TestScoreResponse:
    def test_exact_match(self):
        result = score_response("use flox install", "use flox install")
        assert result["exact_match"] is True
        assert result["keyword_overlap"] == 1.0

    def test_partial_overlap(self):
        result = score_response("use flox install python", "use flox install rust")
        assert result["exact_match"] is False
        assert 0.0 < result["keyword_overlap"] < 1.0

    def test_no_overlap(self):
        result = score_response("kubernetes pods", "python packages")
        assert result["keyword_overlap"] == 0.0
        assert result["exact_match"] is False

    def test_empty_expected(self):
        result = score_response("", "some response")
        assert result["keyword_overlap"] == 0.0


class TestRunEval:
    def test_with_mock_caller(self):
        ground_truth = [
            {"question": "How to install?", "expected_answer": "use flox install", "skill": "core-canon"},
            {"question": "How to deploy?", "expected_answer": "use kubectl apply", "skill": "k8s"},
        ]

        def mock_caller(q: str) -> str:
            if "install" in q:
                return "use flox install"
            return "something else entirely"

        results = run_eval(ground_truth, mock_caller)
        assert results["total"] == 2
        assert results["exact_matches"] == 1
        assert results["mean_keyword_score"] > 0
        assert "core-canon" in results["per_skill"]
        assert results["per_skill"]["core-canon"] == 1.0

    def test_empty_ground_truth(self):
        results = run_eval([], lambda q: "")
        assert results["total"] == 0
        assert results["mean_keyword_score"] == 0.0
