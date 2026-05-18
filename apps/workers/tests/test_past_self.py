"""Past Self service tests.

Plain-text output (no JSON envelope). Tests cover length floor enforcement
and the persistence shape — past content stays in conversations.metadata
AND lands as the user message so subsequent /chat/[id] turns see it in
history.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.llm import LiteLLMError, LiteLLMNetworkError
from app.services.past_self import (
    MIN_REBUTTAL_CHARS,
    PastSelfRun,
    generate_rebuttal,
    persist_past_self_run,
    run_past_self,
)


HOST_SLUG = "devils_advocate"
GOOD_REBUTTAL = "You said you'd never X. " * 20  # ~440 chars


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


# ----- generate_rebuttal ----------------------------------------------------


async def test_generate_returns_rebuttal() -> None:
    llm = FakeLLM(content=GOOD_REBUTTAL)
    out = await generate_rebuttal("Past quote.", client=llm)  # type: ignore[arg-type]
    assert out is not None
    assert "You said" in out


async def test_generate_too_short_returns_none() -> None:
    short = "Brief."
    assert len(short) < MIN_REBUTTAL_CHARS
    llm = FakeLLM(content=short)
    assert await generate_rebuttal("x" * 50, client=llm) is None  # type: ignore[arg-type]


async def test_generate_llm_error_returns_none() -> None:
    llm = FakeLLM(exc=LiteLLMNetworkError("down"))
    assert await generate_rebuttal("x" * 50, client=llm) is None  # type: ignore[arg-type]


async def test_generate_http_error_returns_none() -> None:
    llm = FakeLLM(exc=LiteLLMError("500", 500, "x"))
    assert await generate_rebuttal("x" * 50, client=llm) is None  # type: ignore[arg-type]


# ----- persist + run --------------------------------------------------------


async def test_persist_stashes_past_in_metadata_and_user_message() -> None:
    sb = FakeSupabase()
    sb.seed_host()

    run = PastSelfRun(
        past_content="I'll never go back to that city.",
        rebuttal=GOOD_REBUTTAL,
    )
    persisted = await persist_past_self_run(sb, user_id="u", run=run)  # type: ignore[arg-type]

    convo = sb.table("conversations").rows[0]
    assert convo["mode"] == "past_self"
    assert convo["metadata"]["past_content"] == "I'll never go back to that city."
    assert convo["persona_id"] == "host-id"

    messages = sb.table("messages").rows
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "I'll never go back to that city."
    assert messages[0]["metadata"]["kind"] == "past_self_quote"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["metadata"]["kind"] == "past_self_rebuttal"
    assert persisted.assistant_message_id == messages[1]["id"]


async def test_run_end_to_end_happy() -> None:
    sb = FakeSupabase()
    sb.seed_host()
    llm = FakeLLM(content=GOOD_REBUTTAL)

    run = await run_past_self(
        sb,  # type: ignore[arg-type]
        user_id="u",
        past_content="I used to think X was the answer.",
        client=llm,  # type: ignore[arg-type]
    )

    assert run is not None
    assert run.conversation_id is not None
    assert len(sb.table("messages").rows) == 2


async def test_run_llm_failure_yields_none() -> None:
    sb = FakeSupabase()
    sb.seed_host()
    llm = FakeLLM(exc=LiteLLMNetworkError("down"))
    run = await run_past_self(
        sb,  # type: ignore[arg-type]
        user_id="u",
        past_content="Past content here.",
        client=llm,  # type: ignore[arg-type]
    )
    assert run is None
    assert "conversations" not in sb.tables or sb.tables["conversations"].rows == []
