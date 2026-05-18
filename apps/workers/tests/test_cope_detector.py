"""Cope Detector service tests.

Same shape as decision-killer / steelman — JSON parse, defensive paths,
persistence shape including the rendered markdown body.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.cope_detector import (
    CopeDetectorResult,
    CopeDetectorRun,
    generate_cope_detector,
    persist_cope_detector_run,
    run_cope_detector,
)
from app.services.llm import LiteLLMError, LiteLLMNetworkError


HOST_SLUG = "devils_advocate"

GOOD_PAYLOAD = {
    "telling_yourself": "You're saying you'll start once the calendar clears.",
    "actually_avoiding": "You're scared of finding out the new thing doesn't work.",
    "unasked_question": "What would make you start before the calendar clears?",
}


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


# ----- generate_cope_detector ----------------------------------------------


async def test_generate_parses_well_formed() -> None:
    llm = FakeLLM(content=json.dumps(GOOD_PAYLOAD))
    result = await generate_cope_detector("My excuse.", client=llm)  # type: ignore[arg-type]
    assert result is not None
    assert result.telling_yourself.startswith("You're saying")
    assert result.unasked_question.endswith("?")


async def test_generate_network_error_returns_none() -> None:
    llm = FakeLLM(exc=LiteLLMNetworkError("down"))
    assert await generate_cope_detector("x" * 30, client=llm) is None  # type: ignore[arg-type]


async def test_generate_http_error_returns_none() -> None:
    llm = FakeLLM(exc=LiteLLMError("500", 500, "x"))
    assert await generate_cope_detector("x" * 30, client=llm) is None  # type: ignore[arg-type]


async def test_generate_malformed_json_returns_none() -> None:
    llm = FakeLLM(content="not json")
    assert await generate_cope_detector("x" * 30, client=llm) is None  # type: ignore[arg-type]


async def test_generate_missing_field_returns_none() -> None:
    bad = dict(GOOD_PAYLOAD)
    bad.pop("unasked_question")
    llm = FakeLLM(content=json.dumps(bad))
    assert await generate_cope_detector("x" * 30, client=llm) is None  # type: ignore[arg-type]


# ----- persist + run --------------------------------------------------------


async def test_persist_renders_markdown_body() -> None:
    sb = FakeSupabase()
    sb.seed_host()

    result = CopeDetectorResult(**GOOD_PAYLOAD)
    persisted = await persist_cope_detector_run(
        sb,  # type: ignore[arg-type]
        user_id="u",
        run=CopeDetectorRun(rationalization="Excuse text.", result=result),
    )

    convo = sb.table("conversations").rows[0]
    assert convo["mode"] == "cope_detector"
    assert convo["persona_id"] == "host-id"

    messages = sb.table("messages").rows
    assert len(messages) == 2
    body = messages[1]["content"]
    assert "## What You're Telling Yourself" in body
    assert "## What You're Actually Avoiding" in body
    assert "## The Question You're Not Asking" in body
    meta = messages[1]["metadata"]
    assert meta["kind"] == "cope_detector"
    assert meta["unasked_question"].endswith("?")
    assert persisted.assistant_message_id == messages[1]["id"]


async def test_run_end_to_end() -> None:
    sb = FakeSupabase()
    sb.seed_host()
    llm = FakeLLM(content=json.dumps(GOOD_PAYLOAD))

    run = await run_cope_detector(
        sb,  # type: ignore[arg-type]
        user_id="u",
        rationalization="I'm only delaying because of the timing.",
        client=llm,  # type: ignore[arg-type]
    )

    assert run is not None
    assert len(sb.table("messages").rows) == 2


async def test_run_llm_failure_yields_none() -> None:
    sb = FakeSupabase()
    sb.seed_host()
    llm = FakeLLM(exc=LiteLLMNetworkError("down"))
    run = await run_cope_detector(
        sb,  # type: ignore[arg-type]
        user_id="u",
        rationalization="excuse",
        client=llm,  # type: ignore[arg-type]
    )
    assert run is None
    assert "conversations" not in sb.tables or sb.tables["conversations"].rows == []
