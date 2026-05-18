"""Content moderation service tests."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.llm import LiteLLMError, LiteLLMNetworkError
from app.services.moderation import moderate


class FakeLLM:
    def __init__(self, content: str | None = None, exc: Exception | None = None) -> None:
        self._content = content
        self._exc = exc
        self.calls: list[dict[str, Any]] = []

    async def chat(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        return {"choices": [{"message": {"role": "assistant", "content": self._content}}]}


async def test_moderate_approves_clean_content() -> None:
    payload = {"action": "approve", "reason": "no violations", "categories": ["none"]}
    result = await moderate(
        content="Your LinkedIn headline is four buzzwords and a verb.",
        kind="roast_feed_post",
        client=FakeLLM(content=json.dumps(payload)),  # type: ignore[arg-type]
    )
    assert result.action == "approve"
    assert result.categories == ["none"]


async def test_moderate_rejects_real_person_impersonation() -> None:
    payload = {
        "action": "reject",
        "reason": "names a real person",
        "categories": ["real_person_impersonation"],
    }
    result = await moderate(
        content="x" * 50,
        kind="roast_feed_post",
        client=FakeLLM(content=json.dumps(payload)),  # type: ignore[arg-type]
    )
    assert result.action == "reject"
    assert "real_person_impersonation" in result.categories


async def test_moderate_flags_borderline() -> None:
    payload = {"action": "flag", "reason": "borderline", "categories": ["harassment"]}
    result = await moderate(
        content="x" * 50,
        kind="roast_feed_post",
        client=FakeLLM(content=json.dumps(payload)),  # type: ignore[arg-type]
    )
    assert result.action == "flag"


async def test_moderate_empty_content_rejects() -> None:
    fake = FakeLLM(content="should not be called")
    result = await moderate(
        content="   ",
        kind="roast_feed_post",
        client=fake,  # type: ignore[arg-type]
    )
    assert result.action == "reject"
    assert result.reason == "empty_content"
    assert fake.calls == []


async def test_moderate_llm_error_defaults_to_flag() -> None:
    result = await moderate(
        content="content",
        kind="roast_feed_post",
        client=FakeLLM(exc=LiteLLMNetworkError("down")),  # type: ignore[arg-type]
    )
    assert result.action == "flag"
    assert result.reason == "moderator_call_failed"


async def test_moderate_http_error_defaults_to_flag() -> None:
    result = await moderate(
        content="content",
        kind="roast_feed_post",
        client=FakeLLM(exc=LiteLLMError("500", 500, "x")),  # type: ignore[arg-type]
    )
    assert result.action == "flag"


async def test_moderate_malformed_json_defaults_to_flag() -> None:
    result = await moderate(
        content="content",
        kind="roast_feed_post",
        client=FakeLLM(content="not json"),  # type: ignore[arg-type]
    )
    assert result.action == "flag"


async def test_moderate_invalid_action_enum_defaults_to_flag() -> None:
    payload = {"action": "made_up", "reason": "x", "categories": []}
    result = await moderate(
        content="content",
        kind="roast_feed_post",
        client=FakeLLM(content=json.dumps(payload)),  # type: ignore[arg-type]
    )
    assert result.action == "flag"


async def test_moderate_persona_kind_passes_through() -> None:
    payload = {"action": "approve", "reason": "ok", "categories": ["none"]}
    fake = FakeLLM(content=json.dumps(payload))
    await moderate(
        content="System prompt for a persona...",
        kind="persona_system_prompt",
        client=fake,  # type: ignore[arg-type]
    )
    body = fake.calls[0]["messages"][1]["content"]
    assert "<kind>persona_system_prompt</kind>" in body
