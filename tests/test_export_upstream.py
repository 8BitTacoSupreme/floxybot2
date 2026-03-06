"""Tests for canon upstream export."""

from __future__ import annotations

import json
import tempfile

from scripts.export_upstream import (
    _content_hash,
    anonymize,
    apply_review_gate,
    export_upstream,
    load_votes,
)


class TestAnonymize:
    def test_strips_user_id(self):
        record = {"user_id": "usr_123", "query_text": "hello", "skills_used": ["k8s"]}
        result = anonymize(record)
        assert "user_id" not in result
        assert result["skills_used"] == ["k8s"]

    def test_replaces_home_paths(self):
        record = {"query_text": "error in /Users/alice/project/main.py"}
        result = anonymize(record)
        assert "/Users/alice" not in result["query_text"]
        assert "[PATH]" in result["query_text"]

    def test_removes_ips(self):
        record = {"response_text": "connect to 192.168.1.1 on port 5432"}
        result = anonymize(record)
        assert "192.168.1.1" not in result["response_text"]
        assert "[IP]" in result["response_text"]

    def test_preserves_skill_names(self):
        record = {"skills_used": ["k8s", "terraform"], "vote": "up"}
        result = anonymize(record)
        assert result["skills_used"] == ["k8s", "terraform"]
        assert result["vote"] == "up"

    def test_strips_email(self):
        record = {"email": "user@test.com", "query_text": "help"}
        result = anonymize(record)
        assert "email" not in result


class TestReviewGate:
    def test_none_path_passes_all(self):
        records = [{"a": 1}, {"b": 2}]
        result = apply_review_gate(records, None)
        assert len(result) == 2

    def test_filters_by_hash(self):
        records = [{"query": "hello"}, {"query": "world"}]
        approved_hash = _content_hash(records[0])

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(approved_hash + "\n")
            path = f.name

        result = apply_review_gate(records, path)
        assert len(result) == 1
        assert result[0]["query"] == "hello"


class TestEndToEnd:
    def test_export_with_mock_source(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as src:
            src.write(json.dumps({"user_id": "u1", "query_text": "help at /Users/bob/proj", "vote": "up", "skills_used": ["k8s"]}) + "\n")
            src.write(json.dumps({"user_id": "u2", "query_text": "install", "vote": "up", "skills_used": ["core-canon"]}) + "\n")
            src_path = src.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as out:
            out_path = out.name

        result = export_upstream(src_path, out_path)
        assert len(result) == 2
        # Verify anonymization
        assert all("user_id" not in r for r in result)

        with open(out_path) as f:
            data = json.load(f)
        assert data["count"] == 2
