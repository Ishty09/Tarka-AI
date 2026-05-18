"""Future Self service tests.

Same shape as past_self — plain-text rebuttal with length floor; same
persistence pattern but mode='future_self'.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.future_self import (
    MIN_MESSAGE_CHARS,
    FutureSelfRun,
    generate_future_self_message,
    persist_future_self_run,
    run_future_self,
)
from app.services.llm import LiteLLMError, LiteLLMNetworkError


HOST_SLUG = "devils_advocate"
GOOD_MESSAGE = "You're about to do the thing that costs everything. " * 10  # ~520 chars


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

    def seed_host(self) -> None:
        self.table("personas").rows.append({"id": "host-id", "slug": HOST_SLUG})


async def test_generate_returns_message() -> None:
    llm = FakeLLM(content=GOOD_MESSAGE)
    out = await generate_future_self_message("My decision.", client=llm)  # type: ignore[arg-type]
    assert out is not None
    assert "about to" in out.lower()


async def test_generate_too_short_returns_none() -> None:
    short = "Brief."
    assert len(short) < MIN_MESSAGE_CHARS
    assert (
        await generate_future_self_message("x" * 30, client=FakeLLM(content=short))  # type: ignore[arg-type]
    ) is None


async def test_generate_network_error_returns_none() -> None:
    llm = FakeLLM(exc=LiteLLMNetworkError("down"))
    assert await generate_future_self_message("x" * 30, client=llm) is None  # type: ignore[arg-type]


async def test_generate_http_error_returns_none() -> None:
    llm = FakeLLM(exc=LiteLLMError("500", 500, "x"))
    assert await generate_future_self_message("x" * 30, client=llm) is None  # type: ignore[arg-type]


async def test_persist_writes_two_messages_with_kind_markers() -> None:
    sb = FakeSupabase()
    sb.seed_host()
    persisted = await persist_future_self_run(
        sb,  # type: ignore[arg-type]
        user_id="u",
        run=FutureSelfRun(decision="Quit my job.", message=GOOD_MESSAGE),
    )

    convo = sb.table("conversations").rows[0]
    assert convo["mode"] == "future_self"
    assert convo["metadata"]["decision"] == "Quit my job."
    assert convo["persona_id"] == "host-id"

    messages = sb.table("messages").rows
    assert len(messages) == 2
    assert messages[0]["metadata"]["kind"] == "future_self_decision"
    assert messages[1]["metadata"]["kind"] == "future_self_message"
    assert persisted.assistant_message_id == messages[1]["id"]


async def test_run_end_to_end_happy() -> None:
    sb = FakeSupabase()
    sb.seed_host()
    run = await run_future_self(
        sb,  # type: ignore[arg-type]
        user_id="u",
        decision="Should I move cities for this job?",
        client=FakeLLM(content=GOOD_MESSAGE),  # type: ignore[arg-type]
    )
    assert run is not None
    assert len(sb.table("messages").rows) == 2


async def test_run_llm_failure_yields_none() -> None:
    sb = FakeSupabase()
    sb.seed_host()
    run = await run_future_self(
        sb,  # type: ignore[arg-type]
        user_id="u",
        decision="x" * 30,
        client=FakeLLM(exc=LiteLLMNetworkError("down")),  # type: ignore[arg-type]
    )
    assert run is None
    assert "conversations" not in sb.tables or sb.tables["conversations"].rows == []
