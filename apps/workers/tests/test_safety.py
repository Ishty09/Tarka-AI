"""Safety screen + redaction tests.

We stub the LiteLLM client rather than hitting the proxy. Each test sets up
the response the classifier would have produced and asserts the parsed
SafetyResult plus the redacted text.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.services import llm as llm_module
from app.services.llm import LiteLLMError, LiteLLMNetworkError
from app.services.safety import (
    Redaction,
    SafetyResult,
    classify_message,
    redact,
)


class FakeLLM:
    """Drop-in for LiteLLMClient.chat — returns a canned response or raises."""

    def __init__(self, content: str | None = None, exc: Exception | None = None) -> None:
        self._content = content
        self._exc = exc
        self.calls: list[dict[str, Any]] = []

    async def chat(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        return {
            "choices": [{"message": {"role": "assistant", "content": self._content}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


@pytest.fixture(autouse=True)
def _clear_llm_singleton() -> None:
    llm_module.set_llm_client(None)
    yield
    llm_module.set_llm_client(None)


# ----- classify_message ------------------------------------------------------


async def test_safe_verdict_parsed() -> None:
    payload = {
        "verdict": "safe",
        "confidence": 0.95,
        "reason": "no concerning content",
        "redactions": [],
    }
    fake = FakeLLM(content=json.dumps(payload))
    result = await classify_message("hello there", client=fake)  # type: ignore[arg-type]
    assert result == SafetyResult(**payload)
    assert fake.calls, "classifier should have been called"


async def test_crisis_verdict_parsed() -> None:
    payload = {
        "verdict": "crisis",
        "confidence": 0.88,
        "reason": "suicidal ideation",
        "redactions": [],
    }
    fake = FakeLLM(content=json.dumps(payload))
    result = await classify_message("...", client=fake)  # type: ignore[arg-type]
    assert result.verdict == "crisis"
    assert result.confidence == pytest.approx(0.88)


async def test_redactions_parsed() -> None:
    payload = {
        "verdict": "safe",
        "confidence": 0.9,
        "reason": "ok",
        "redactions": [
            {"start": 5, "end": 19, "category": "email"},
        ],
    }
    fake = FakeLLM(content=json.dumps(payload))
    result = await classify_message("call me@example.com today", client=fake)  # type: ignore[arg-type]
    assert len(result.redactions) == 1
    assert result.redactions[0].category == "email"


async def test_empty_input_short_circuits() -> None:
    fake = FakeLLM(content="should not be parsed")
    result = await classify_message("   ", client=fake)  # type: ignore[arg-type]
    assert result.verdict == "safe"
    assert fake.calls == [], "empty inputs should not hit the model"


# ----- defensive deny paths --------------------------------------------------


async def test_llm_network_error_returns_deny() -> None:
    fake = FakeLLM(exc=LiteLLMNetworkError("connection refused"))
    result = await classify_message("hi", client=fake)  # type: ignore[arg-type]
    assert result.verdict == "jailbreak"
    assert "defensive_deny" in result.reason


async def test_llm_http_error_returns_deny() -> None:
    fake = FakeLLM(exc=LiteLLMError("upstream 500", 500, "boom"))
    result = await classify_message("hi", client=fake)  # type: ignore[arg-type]
    assert result.verdict == "jailbreak"


async def test_malformed_json_returns_deny() -> None:
    fake = FakeLLM(content="this is not json")
    result = await classify_message("hi", client=fake)  # type: ignore[arg-type]
    assert result.verdict == "jailbreak"


async def test_schema_violation_returns_deny() -> None:
    fake = FakeLLM(content=json.dumps({"verdict": "not_a_verdict"}))
    result = await classify_message("hi", client=fake)  # type: ignore[arg-type]
    assert result.verdict == "jailbreak"


async def test_anthropic_content_blocks_accepted() -> None:
    """LiteLLM may pass through Anthropic-shape content blocks."""

    payload = json.dumps({
        "verdict": "safe",
        "confidence": 1.0,
        "reason": "ok",
        "redactions": [],
    })

    class BlockLLM:
        async def chat(self, **kwargs: Any) -> dict[str, Any]:
            return {
                "choices": [
                    {"message": {"role": "assistant", "content": [{"type": "text", "text": payload}]}}
                ],
            }

    result = await classify_message("hi", client=BlockLLM())  # type: ignore[arg-type]
    assert result.verdict == "safe"


# ----- redact ----------------------------------------------------------------


def test_redact_single_span() -> None:
    text = "call me@example.com today"
    # "me@example.com" occupies indices 5..19 (end-exclusive).
    spans = [Redaction(start=5, end=19, category="email")]
    assert redact(text, spans) == "call [REDACTED] today"


def test_redact_multiple_non_overlapping() -> None:
    text = "phone 555-1212 email a@b.co"
    spans = [
        Redaction(start=6, end=14, category="phone"),
        Redaction(start=21, end=27, category="email"),
    ]
    assert redact(text, spans) == "phone [REDACTED] email [REDACTED]"


def test_redact_out_of_range_skipped() -> None:
    text = "short"
    spans = [Redaction(start=100, end=200, category="phone")]
    assert redact(text, spans) == "short"


def test_redact_overlap_prefers_longer_span() -> None:
    text = "abcdefghij"
    spans = [
        Redaction(start=2, end=5, category="phone"),
        Redaction(start=2, end=8, category="phone"),
    ]
    # Longer span (end=8) wins because of (start, -end) sort.
    assert redact(text, spans) == "ab[REDACTED]ij"


def test_redact_empty_passthrough() -> None:
    assert redact("anything", []) == "anything"
