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
    embed_facts,
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


class _Res:
    def __init__(self, data: Any) -> None:
        self.data = data


class FakeQuery:
    def __init__(self, table: "FakeTable", op: str, payload: Any = None) -> None:
        self._table = table
        self._op = op
        self._payload = payload
        self._filters: list[tuple[str, Any]] = []

    def eq(self, col: str, val: Any) -> "FakeQuery":
        self._filters.append((col, val))
        return self

    async def execute(self) -> _Res:
        if self._op == "insert":
            payload = (
                self._payload if isinstance(self._payload, list) else [self._payload]
            )
            inserted: list[dict[str, Any]] = []
            for row in payload:
                new_row = dict(row)
                if "id" not in new_row:
                    new_row["id"] = len(self._table.rows) + 1
                self._table.rows.append(new_row)
                inserted.append(new_row)
            return _Res(inserted)

        if self._op == "update":
            for row in self._table.rows:
                if all(row.get(c) == v for c, v in self._filters):
                    row.update(self._payload)
            return _Res([])

        return _Res([])


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def insert(self, payload: Any) -> FakeQuery:
        return FakeQuery(self, "insert", payload)

    def update(self, payload: Any) -> FakeQuery:
        return FakeQuery(self, "update", payload)


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
    assert len(inserted) == 2
    assert inserted[0][1] == "User believes X."
    rows = sb.table("user_facts").rows
    assert len(rows) == 2
    assert rows[0]["fact"] == "User believes X."
    assert rows[0]["user_id"] == "user-1"
    assert rows[0]["source_message_id"] == 42
    assert rows[0]["is_active"] is True
    assert rows[0]["superseded_by"] is None


async def test_persist_empty_no_op() -> None:
    sb = FakeSupabase()
    inserted = await persist_facts(sb, user_id="u", source_message_id=1, facts=[])  # type: ignore[arg-type]
    assert inserted == []
    assert "user_facts" not in sb.tables


# ----- embed_facts -----------------------------------------------------------


class EmbedLLM:
    """Stub LLM with an embed() that returns deterministic vectors."""

    def __init__(self, dim: int = 1536, exc: Exception | None = None) -> None:
        self._dim = dim
        self._exc = exc
        self.calls: list[dict[str, Any]] = []

    async def embed(self, **kwargs: Any) -> list[list[float]]:
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        inputs = kwargs["input"]
        if isinstance(inputs, str):
            inputs = [inputs]
        return [[float(i + 1) / 10.0] * self._dim for i, _ in enumerate(inputs)]


async def test_embed_facts_updates_each_row() -> None:
    sb = FakeSupabase()
    sb.table("user_facts").rows.extend([
        {"id": 1, "fact": "a"},
        {"id": 2, "fact": "b"},
    ])
    llm = EmbedLLM()
    updated = await embed_facts(
        sb,  # type: ignore[arg-type]
        facts=[(1, "a"), (2, "b")],
        client=llm,  # type: ignore[arg-type]
    )
    assert updated == 2
    rows = {r["id"]: r for r in sb.table("user_facts").rows}
    assert rows[1]["embedding"][0] == pytest.approx(0.1)
    assert rows[2]["embedding"][0] == pytest.approx(0.2)


async def test_embed_facts_empty_no_op() -> None:
    sb = FakeSupabase()
    llm = EmbedLLM()
    assert await embed_facts(sb, facts=[], client=llm) == 0  # type: ignore[arg-type]
    assert llm.calls == []


async def test_embed_facts_llm_error_no_update() -> None:
    sb = FakeSupabase()
    sb.table("user_facts").rows.append({"id": 1, "fact": "a"})
    llm = EmbedLLM(exc=LiteLLMNetworkError("down"))
    updated = await embed_facts(
        sb,  # type: ignore[arg-type]
        facts=[(1, "a")],
        client=llm,  # type: ignore[arg-type]
    )
    assert updated == 0
    assert "embedding" not in sb.table("user_facts").rows[0]


async def test_embed_facts_length_mismatch_aborts() -> None:
    sb = FakeSupabase()
    sb.table("user_facts").rows.append({"id": 1, "fact": "a"})

    class ShortLLM:
        async def embed(self, **kwargs: Any) -> list[list[float]]:
            return []  # zero vectors returned for one input

    updated = await embed_facts(
        sb,  # type: ignore[arg-type]
        facts=[(1, "a")],
        client=ShortLLM(),  # type: ignore[arg-type]
    )
    assert updated == 0


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

    class FakeChatPlusEmbed(FakeLLM):
        async def embed(self, **kwargs: Any) -> list[list[float]]:
            return [[0.1] * 1536]

    fake = FakeChatPlusEmbed(content=json.dumps(payload))
    count = await extract_and_persist(
        user_id="u",
        conversation_id="c",
        user_message="I'm an engineer.",
        source_message_id=10,
        client=fake,  # type: ignore[arg-type]
        supabase=sb,  # type: ignore[arg-type]
    )
    assert count == 1
    rows = sb.table("user_facts").rows
    assert len(rows) == 1
    # embed_facts wrote the vector via .update().eq(id, ...).
    assert rows[0].get("embedding") == [0.1] * 1536


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
