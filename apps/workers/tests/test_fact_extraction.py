"""Fact extraction unit tests.

Stubs the LLM and Supabase. We don't need the full integration here —
test_chat_stream covers the asyncio scheduling separately.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.services import llm as llm_module
from app.services.fact_extraction import (
    ExtractedFact,
    extract_and_persist,
    extract_facts,
    persist_facts,
)
from app.services.llm import LiteLLMError, LiteLLMNetworkError


class FakeLLM:
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
        }


class FakeQuery:
    def __init__(self, table: "FakeTable", op: str, payload: Any = None) -> None:
        self._table = table
        self._op = op
        self._payload = payload

    async def execute(self) -> Any:
        if self._op == "insert":
            payload = (
                self._payload if isinstance(self._payload, list) else [self._payload]
            )
            self._table.rows.extend(payload)

        class _Res:
            data: Any = []

        return _Res()


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def insert(self, payload: Any) -> FakeQuery:
        return FakeQuery(self, "insert", payload)


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}

    def table(self, name: str) -> FakeTable:
        if name not in self.tables:
            self.tables[name] = FakeTable()
        return self.tables[name]


@pytest.fixture(autouse=True)
def _clear_llm() -> None:
    llm_module.set_llm_client(None)
    yield
    llm_module.set_llm_client(None)


# ----- extract_facts ---------------------------------------------------------


async def test_extracts_well_formed_facts() -> None:
    payload = {
        "facts": [
            {
                "fact": "User said they hate their job.",
                "category": "belief",
                "confidence": 0.9,
                "supersedes_fact_id": None,
            },
            {
                "fact": "User committed to quit by Friday.",
                "category": "commitment",
                "confidence": 0.85,
                "supersedes_fact_id": None,
            },
        ]
    }
    fake = FakeLLM(content=json.dumps(payload))
    result = await extract_facts("I hate this job and I'm quitting Friday.", client=fake)  # type: ignore[arg-type]
    assert len(result.facts) == 2
    assert result.facts[0].category == "belief"
    assert result.facts[1].category == "commitment"


async def test_empty_message_skips_llm() -> None:
    fake = FakeLLM(content="should not be parsed")
    result = await extract_facts("   ", client=fake)  # type: ignore[arg-type]
    assert result.facts == []
    assert fake.calls == []


async def test_llm_error_returns_empty() -> None:
    fake = FakeLLM(exc=LiteLLMNetworkError("boom"))
    result = await extract_facts("hi", client=fake)  # type: ignore[arg-type]
    assert result.facts == []


async def test_llm_http_error_returns_empty() -> None:
    fake = FakeLLM(exc=LiteLLMError("500", 500, "x"))
    result = await extract_facts("hi", client=fake)  # type: ignore[arg-type]
    assert result.facts == []


async def test_malformed_json_returns_empty() -> None:
    fake = FakeLLM(content="this is not JSON")
    result = await extract_facts("hi", client=fake)  # type: ignore[arg-type]
    assert result.facts == []


async def test_schema_invalid_returns_empty() -> None:
    fake = FakeLLM(
        content=json.dumps({"facts": [{"fact": "x", "category": "made_up", "confidence": 0.5}]})
    )
    result = await extract_facts("hi", client=fake)  # type: ignore[arg-type]
    assert result.facts == []


async def test_invalid_confidence_rejects_entire_batch() -> None:
    fake = FakeLLM(
        content=json.dumps(
            {
                "facts": [
                    {
                        "fact": "x",
                        "category": "belief",
                        "confidence": 1.5,
                        "supersedes_fact_id": None,
                    }
                ]
            }
        )
    )
    result = await extract_facts("hi", client=fake)  # type: ignore[arg-type]
    assert result.facts == []


# ----- persist_facts ---------------------------------------------------------


async def test_persist_inserts_correct_rows() -> None:
    sb = FakeSupabase()
    facts = [
        ExtractedFact(fact="User believes X.", category="belief", confidence=0.9),
        ExtractedFact(fact="User wants Y.", category="goal", confidence=0.7),
    ]
    inserted = await persist_facts(
        sb,  # type: ignore[arg-type]
        user_id="user-1",
        source_message_id=42,
        facts=facts,
    )
    assert inserted == 2
    rows = sb.table("user_facts").rows
    assert len(rows) == 2
    assert rows[0]["fact"] == "User believes X."
    assert rows[0]["user_id"] == "user-1"
    assert rows[0]["source_message_id"] == 42
    assert rows[0]["is_active"] is True
    assert rows[0]["superseded_by"] is None
    assert "embedding" not in rows[0]  # step 14 fills


async def test_persist_empty_no_op() -> None:
    sb = FakeSupabase()
    inserted = await persist_facts(sb, user_id="u", source_message_id=1, facts=[])  # type: ignore[arg-type]
    assert inserted == 0
    assert "user_facts" not in sb.tables


# ----- extract_and_persist (end-to-end glue) --------------------------------


async def test_end_to_end_glue() -> None:
    sb = FakeSupabase()
    payload = {
        "facts": [
            {
                "fact": "User is an engineer.",
                "category": "identity",
                "confidence": 0.95,
                "supersedes_fact_id": None,
            }
        ]
    }
    fake = FakeLLM(content=json.dumps(payload))
    count = await extract_and_persist(
        user_id="u",
        conversation_id="c",
        user_message="I'm an engineer.",
        source_message_id=10,
        client=fake,  # type: ignore[arg-type]
        supabase=sb,  # type: ignore[arg-type]
    )
    assert count == 1
    assert len(sb.table("user_facts").rows) == 1


async def test_end_to_end_no_facts_skips_persist() -> None:
    sb = FakeSupabase()
    fake = FakeLLM(content=json.dumps({"facts": []}))
    count = await extract_and_persist(
        user_id="u",
        conversation_id="c",
        user_message="hi",
        source_message_id=1,
        client=fake,  # type: ignore[arg-type]
        supabase=sb,  # type: ignore[arg-type]
    )
    assert count == 0
    assert "user_facts" not in sb.tables
