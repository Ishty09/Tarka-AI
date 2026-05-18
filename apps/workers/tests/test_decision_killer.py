"""Decision Killer service tests.

Same shape as test_steelman — JSON parse, defensive paths, persistence.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.decision_killer import (
    DecisionKillerResult,
    DecisionKillerRun,
    WrongReason,
    generate_decision_killer,
    persist_decision_killer_run,
    run_decision_killer,
)
from app.services.llm import LiteLLMError, LiteLLMNetworkError


HOST_SLUG = "devils_advocate"

GOOD_PAYLOAD = {
    "reasons_wrong": [
        {"reason": "Sunk cost", "argument": "You're optimising for what you've already spent."},
        {"reason": "Wrong horizon", "argument": "12 months is too short for this kind of bet."},
        {"reason": "Identity bias", "argument": "You're picking the option that confirms who you think you are."},
    ],
    "one_reason_right": "If the timing constraint is real, this is the only path that fits the next 90 days.",
    "actual_avoidance": "You're avoiding the conversation with your co-founder.",
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


# ----- generate_decision_killer ---------------------------------------------


async def test_generate_parses_well_formed() -> None:
    llm = FakeLLM(content=json.dumps(GOOD_PAYLOAD))
    result = await generate_decision_killer("My decision.", client=llm)  # type: ignore[arg-type]
    assert result is not None
    assert len(result.reasons_wrong) == 3
    assert result.reasons_wrong[0].reason == "Sunk cost"
    assert "co-founder" in result.actual_avoidance


async def test_generate_rejects_two_reasons() -> None:
    bad = dict(GOOD_PAYLOAD)
    bad["reasons_wrong"] = GOOD_PAYLOAD["reasons_wrong"][:2]  # only 2 — min/max are 3
    llm = FakeLLM(content=json.dumps(bad))
    assert await generate_decision_killer("x" * 30, client=llm) is None  # type: ignore[arg-type]


async def test_generate_rejects_four_reasons() -> None:
    bad = dict(GOOD_PAYLOAD)
    extra: list[dict[str, str]] = list(GOOD_PAYLOAD["reasons_wrong"])  # type: ignore[arg-type]
    extra.append({"reason": "Extra", "argument": "Extra arg"})
    bad["reasons_wrong"] = extra
    llm = FakeLLM(content=json.dumps(bad))
    assert await generate_decision_killer("x" * 30, client=llm) is None  # type: ignore[arg-type]


async def test_generate_network_error_returns_none() -> None:
    llm = FakeLLM(exc=LiteLLMNetworkError("down"))
    assert await generate_decision_killer("x" * 30, client=llm) is None  # type: ignore[arg-type]


async def test_generate_http_error_returns_none() -> None:
    llm = FakeLLM(exc=LiteLLMError("500", 500, "x"))
    assert await generate_decision_killer("x" * 30, client=llm) is None  # type: ignore[arg-type]


async def test_generate_malformed_json_returns_none() -> None:
    llm = FakeLLM(content="not json")
    assert await generate_decision_killer("x" * 30, client=llm) is None  # type: ignore[arg-type]


# ----- persist + run --------------------------------------------------------


async def test_persist_writes_markdown_content_and_metadata() -> None:
    sb = FakeSupabase()
    sb.seed_host()

    result = DecisionKillerResult(
        reasons_wrong=[
            WrongReason(reason=f"R{i}", argument=f"A{i}") for i in range(1, 4)
        ],
        one_reason_right="The case for going ahead.",
        actual_avoidance="You're avoiding X.",
    )
    persisted = await persist_decision_killer_run(
        sb,  # type: ignore[arg-type]
        user_id="u",
        run=DecisionKillerRun(decision="My decision.", result=result),
    )

    convo = sb.table("conversations").rows[0]
    assert convo["mode"] == "decision_killer"
    assert convo["persona_id"] == "host-id"

    messages = sb.table("messages").rows
    assert len(messages) == 2
    body = messages[1]["content"]
    # Headings rendered into the assistant content for /chat/[id] readability.
    assert "## 3 Reasons This Is Wrong" in body
    assert "## 1 Reason It Might Be Right" in body
    assert "## What You're Actually Avoiding" in body
    meta = messages[1]["metadata"]
    assert meta["kind"] == "decision_killer"
    assert len(meta["reasons_wrong"]) == 3
    assert meta["actual_avoidance"] == "You're avoiding X."


async def test_run_end_to_end_happy_path() -> None:
    sb = FakeSupabase()
    sb.seed_host()
    llm = FakeLLM(content=json.dumps(GOOD_PAYLOAD))

    run = await run_decision_killer(
        sb,  # type: ignore[arg-type]
        user_id="u",
        decision="Should I quit my job to chase this?",
        client=llm,  # type: ignore[arg-type]
    )

    assert run is not None
    assert len(sb.table("messages").rows) == 2


async def test_run_llm_failure_returns_none_no_persistence() -> None:
    sb = FakeSupabase()
    sb.seed_host()
    llm = FakeLLM(exc=LiteLLMNetworkError("down"))
    run = await run_decision_killer(
        sb,  # type: ignore[arg-type]
        user_id="u",
        decision="Should I do it?",
        client=llm,  # type: ignore[arg-type]
    )
    assert run is None
    assert "conversations" not in sb.tables or sb.tables["conversations"].rows == []
