"""Tests for multi-signal intent classification."""

from __future__ import annotations

import pytest

from src.models.types import Intent, BuiltContext
from src.router.intent import score_intent, classify_intent


def _msg(text: str, code_blocks: list[str] | None = None) -> dict:
    return {
        "content": {
            "text": text,
            "code_blocks": code_blocks or [],
        }
    }


def _ctx() -> BuiltContext:
    return BuiltContext()


class TestCodeGenerationIntent:
    def test_code_blocks_trigger_code_gen(self):
        result = score_intent(_msg("here's my config", ["[install]\npython3 = {}"]), _ctx(), [])
        assert result.intent == Intent.CODE_GENERATION

    def test_manifest_keyword(self):
        result = score_intent(_msg("edit my manifest to add nodejs"), _ctx(), [])
        assert result.intent == Intent.CODE_GENERATION

    def test_generate_keyword(self):
        result = score_intent(_msg("generate a hook for postgres"), _ctx(), [])
        assert result.intent == Intent.CODE_GENERATION

    def test_write_keyword(self):
        result = score_intent(_msg("write a service definition"), _ctx(), [])
        assert result.intent == Intent.CODE_GENERATION


class TestDiagnosticIntent:
    def test_error_keyword(self):
        result = score_intent(_msg("I get an error when activating"), _ctx(), [])
        assert result.intent == Intent.DIAGNOSTIC

    def test_not_working(self):
        result = score_intent(_msg("flox activate is not working"), _ctx(), [])
        assert result.intent == Intent.DIAGNOSTIC

    def test_debug_keyword(self):
        result = score_intent(_msg("help me debug this manifest"), _ctx(), [])
        assert result.intent == Intent.DIAGNOSTIC

    def test_code_blocks_plus_error_is_diagnostic(self):
        """Code blocks + error keywords = diagnostic, not code gen."""
        result = score_intent(
            _msg("I get this error:", ["error: attribute not found"]), _ctx(), []
        )
        assert result.intent == Intent.DIAGNOSTIC


class TestTeachingIntent:
    def test_how_keyword(self):
        result = score_intent(_msg("how do environments work?"), _ctx(), [])
        assert result.intent == Intent.TEACHING

    def test_explain_keyword(self):
        result = score_intent(_msg("explain the difference between flox and nix"), _ctx(), [])
        assert result.intent == Intent.TEACHING

    def test_what_is_keyword(self):
        result = score_intent(_msg("what is a manifest.toml?"), _ctx(), [])
        # "what is" triggers teaching, but "manifest" triggers code_gen
        # both score 0.3 — hybrid falls to CONVERSATIONAL
        assert result.intent in (Intent.TEACHING, Intent.CONVERSATIONAL)


class TestConversationalIntent:
    def test_simple_question(self):
        result = score_intent(_msg("thanks, that helped!"), _ctx(), [])
        assert result.intent == Intent.CONVERSATIONAL

    def test_question_mark_boost(self):
        result = score_intent(_msg("is flox free?"), _ctx(), [])
        assert result.intent == Intent.CONVERSATIONAL

    def test_empty_text(self):
        result = score_intent(_msg(""), _ctx(), [])
        assert result.intent == Intent.CONVERSATIONAL


class TestEscalation:
    def test_billing_triggers_escalation(self):
        result = score_intent(_msg("I need help with billing"), _ctx(), [])
        # Escalation returns CONVERSATIONAL with confidence 1.0
        assert result.intent == Intent.CONVERSATIONAL
        assert result.confidence == 1.0

    def test_account_triggers_escalation(self):
        result = score_intent(_msg("how do I cancel my account"), _ctx(), [])
        assert result.confidence == 1.0

    def test_security_triggers_escalation(self):
        result = score_intent(_msg("security vulnerability in my environment"), _ctx(), [])
        assert result.confidence == 1.0


class TestHybridDetection:
    def test_hybrid_falls_to_conversational(self):
        """When top two intents are close, pick CONVERSATIONAL."""
        # "error" hits DIAGNOSTIC (0.5), "explain" hits TEACHING (0.5) — tie → hybrid
        result = score_intent(_msg("explain this error"), _ctx(), [])
        assert result.intent == Intent.CONVERSATIONAL

    def test_clear_winner_not_hybrid(self):
        """When one intent clearly dominates, no hybrid."""
        result = score_intent(
            _msg("generate code", ["print('hello')"]), _ctx(), []
        )
        # code_blocks (0.4) + keyword (0.3) = 0.7 for CODE_GENERATION
        assert result.intent == Intent.CODE_GENERATION


class TestClassifyIntentAsync:
    @pytest.mark.asyncio
    async def test_classify_returns_intent(self):
        intent = await classify_intent(_msg("hello"), _ctx(), [])
        assert isinstance(intent, Intent)
