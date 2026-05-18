"""Steelman service tests.

Stubs the LLM and Supabase. Single-shot tool — the orchestration is
thinner than Council; we cover the JSON parse, defensive paths, and
persistence shape.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.llm import LiteLLMError, LiteLLMNetworkError
from app.services.steelman import (
    HOST_PERSONA_SLUG,
    SteelmanCounter,
    SteelmanResult,
    SteelmanRun,
    generate_steelman,
    persist_steelman_run,
    run_steelman,
)


GOOD_PAYLOAD = {
    "strongest_version": "Your position, rebuilt: " + ("X " * 30),
    "assumptions": ["The market behaves rationally", "Sunk costs are recoverable"],
    "evidence": ["Past quarter's churn data", "Industry benchmark for retention"],
    "counters": [
        {"counter": "Counter A", "response": "Response A"},
        {"counter": "Counter B", "response": "Response B"},
        {"counter": "Counter C", "response": "Response C"},
    ],
}


# ----- LLM stub --------------------------------------------------------------


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


# ----- Supabase fake --------------------------------------------------------


class _Res:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, table: "_Table", op: str, payload: Any = None) -> None:
        self._table = table
        self._op = op
        self._payload = payload
        self._filters: list[tuple[str, Any]] = []
        self._limit: int | None = None
        self._maybe_single = False

    def select(self, _cols: str = "*") -> "_Query":
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, val))
        return self

    def limit(self, n: int) -> "_Query":
        self._limit = n
        return self

    def maybe_single(self) -> "_Query":
        self._maybe_single = True
        return self

    async def execute(self) -> _Res:
        if self._op == "select":
            rows = list(self._table.rows)
            for col, val in self._filters:
                rows = [r for r in rows if r.get(col) == val]
            if self._limit is not None:
                rows = rows[: self._limit]
            if self._maybe_single:
                return _Res(rows[0] if rows else None)
            return _Res(rows)

        if self._op == "insert":
            payload = self._payload if isinstance(self._payload, list) else [self._payload]
            inserted: list[dict[str, Any]] = []
            for row in payload:
                new_row = dict(row)
                if "id" not in new_row and self._table.name == "messages":
                    new_row["id"] = len(self._table.rows) + 1
                self._table.rows.append(new_row)
                inserted.append(new_row)
            return _Res(inserted)

        return _Res([])


class _Table:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, _cols: str = "*") -> _Query:
        return _Query(self, "select")

    def insert(self, payload: Any) -> _Query:
        return _Query(self, "insert", payload)


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, _Table] = {}

    def table(self, name: str) -> _Table:
        if name not in self.tables:
            self.tables[name] = _Table(name)
        return self.tables[name]

    def seed_host_persona(self) -> None:
        self.table("personas").rows.append(
            {"id": "host-persona-id", "slug": HOST_PERSONA_SLUG}
        )


# ----- generate_steelman ----------------------------------------------------


async def test_generate_parses_well_formed_output() -> None:
    llm = FakeLLM(content=json.dumps(GOOD_PAYLOAD))
    result = await generate_steelman("My weak position.", client=llm)  # type: ignore[arg-type]
    assert result is not None
    assert "Your position" in result.strongest_version
    assert len(result.assumptions) == 2
    assert len(result.counters) == 3
    assert result.counters[0].counter == "Counter A"


async def test_generate_returns_none_on_llm_error() -> None:
    llm = FakeLLM(exc=LiteLLMNetworkError("down"))
    assert await generate_steelman("x" * 30, client=llm) is None  # type: ignore[arg-type]


async def test_generate_returns_none_on_http_error() -> None:
    llm = FakeLLM(exc=LiteLLMError("500", 500, "x"))
    assert await generate_steelman("x" * 30, client=llm) is None  # type: ignore[arg-type]


async def test_generate_returns_none_on_malformed_json() -> None:
    llm = FakeLLM(content="not json")
    assert await generate_steelman("x" * 30, client=llm) is None  # type: ignore[arg-type]


async def test_generate_returns_none_on_schema_violation() -> None:
    bad = dict(GOOD_PAYLOAD)
    bad["counters"] = []  # min_length=1
    llm = FakeLLM(content=json.dumps(bad))
    assert await generate_steelman("x" * 30, client=llm) is None  # type: ignore[arg-type]


# ----- persist + run --------------------------------------------------------


async def test_persist_inserts_conversation_and_two_messages() -> None:
    sb = FakeSupabase()
    sb.seed_host_persona()

    run = SteelmanRun(
        position="My weak position.",
        result=SteelmanResult(
            strongest_version="Strong version " * 5,
            assumptions=["A"],
            evidence=["E"],
            counters=[SteelmanCounter(counter="C", response="R")],
        ),
    )
    persisted = await persist_steelman_run(sb, user_id="u", run=run)  # type: ignore[arg-type]

    assert persisted.conversation_id is not None
    assert persisted.assistant_message_id is not None

    convo = sb.table("conversations").rows[0]
    assert convo["mode"] == "steelman"
    assert convo["persona_id"] == "host-persona-id"
    assert convo["metadata"]["tool"] == "steelman"

    messages = sb.table("messages").rows
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "My weak position."
    assert messages[1]["role"] == "assistant"
    assert messages[1]["metadata"]["kind"] == "steelman"
    assert messages[1]["metadata"]["counters"][0]["counter"] == "C"


async def test_run_steelman_end_to_end() -> None:
    sb = FakeSupabase()
    sb.seed_host_persona()
    llm = FakeLLM(content=json.dumps(GOOD_PAYLOAD))

    run = await run_steelman(
        sb,  # type: ignore[arg-type]
        user_id="u",
        position="My weak position." + " more context " * 5,
        client=llm,  # type: ignore[arg-type]
    )

    assert run is not None
    assert run.conversation_id is not None
    assert len(sb.table("messages").rows) == 2


async def test_run_steelman_llm_failure_returns_none_no_persistence() -> None:
    sb = FakeSupabase()
    sb.seed_host_persona()
    llm = FakeLLM(exc=LiteLLMNetworkError("down"))

    run = await run_steelman(
        sb,  # type: ignore[arg-type]
        user_id="u",
        position="My weak position.",
        client=llm,  # type: ignore[arg-type]
    )

    assert run is None
    # Nothing persisted on failure.
    assert "conversations" not in sb.tables or sb.tables["conversations"].rows == []
