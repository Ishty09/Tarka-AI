"""Breakup Analyzer service tests.

Covers JSON parse, defensive paths, schema enforcement (3 missing_things),
persistence shape (markdown body + structured metadata).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.breakup_analyzer import (
    BreakupAnalyzerResult,
    BreakupAnalyzerRun,
    generate_breakup_analysis,
    persist_breakup_analyzer_run,
    run_breakup_analyzer,
)
from app.services.llm import LiteLLMError, LiteLLMNetworkError


HOST_SLUG = "devils_advocate"

GOOD_PAYLOAD = {
    "attachment_dynamics": {
        "user": "anxious",
        "partner": "avoidant",
        "summary": "You're flooding the channel; they're going quiet. Classic anxious-avoidant chase.",
    },
    "reconciliation_likelihood": "low",
    "reconciliation_reasoning": (
        "Their messages got shorter every reply. The 'need space' line was the third one in a week."
    ),
    "missing_things": [
        "You're treating their silence as an attack instead of a regulation strategy.",
        "Three of your last four messages were apologies for the previous one.",
        "You haven't asked what they actually want from this — only what they want from you.",
    ],
    "suggested_message": {
        "intent": "end",
        "text": (
            "I'm going to stop chasing you for now. I think we've been doing the same loop for weeks "
            "and it's making both of us worse. If you ever want to talk, I'm here — but I'm not going "
            "to keep texting first."
        ),
    },
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
        return {"choices": [{"message": {"role": "assistant", "content": self._content}}]}


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


def _base_kwargs() -> dict[str, Any]:
    return {
        "text_thread": "Long thread of texts" + (" foo" * 20),
        "duration": "2 years",
        "user_age": 29,
        "partner_age": 31,
        "intent": "repair",
    }


# ----- generate_breakup_analysis -------------------------------------------


async def test_generate_parses_well_formed_output() -> None:
    llm = FakeLLM(content=json.dumps(GOOD_PAYLOAD))
    result = await generate_breakup_analysis(
        **_base_kwargs(),
        client=llm,  # type: ignore[arg-type]
    )
    assert result is not None
    assert result.attachment_dynamics.user == "anxious"
    assert result.reconciliation_likelihood == "low"
    assert len(result.missing_things) == 3
    assert result.suggested_message.intent == "end"


async def test_generate_empty_thread_returns_none() -> None:
    llm = FakeLLM(content="should not be called")
    kwargs = _base_kwargs()
    kwargs["text_thread"] = "   "
    result = await generate_breakup_analysis(**kwargs, client=llm)  # type: ignore[arg-type]
    assert result is None
    assert llm.calls == []


async def test_generate_network_error_returns_none() -> None:
    llm = FakeLLM(exc=LiteLLMNetworkError("down"))
    assert (
        await generate_breakup_analysis(**_base_kwargs(), client=llm)  # type: ignore[arg-type]
    ) is None


async def test_generate_http_error_returns_none() -> None:
    llm = FakeLLM(exc=LiteLLMError("500", 500, "x"))
    assert (
        await generate_breakup_analysis(**_base_kwargs(), client=llm)  # type: ignore[arg-type]
    ) is None


async def test_generate_malformed_json_returns_none() -> None:
    llm = FakeLLM(content="not json")
    assert (
        await generate_breakup_analysis(**_base_kwargs(), client=llm)  # type: ignore[arg-type]
    ) is None


async def test_generate_rejects_two_missing_things() -> None:
    bad = dict(GOOD_PAYLOAD)
    bad["missing_things"] = GOOD_PAYLOAD["missing_things"][:2]  # type: ignore[arg-type]
    llm = FakeLLM(content=json.dumps(bad))
    assert (
        await generate_breakup_analysis(**_base_kwargs(), client=llm)  # type: ignore[arg-type]
    ) is None


async def test_generate_rejects_four_missing_things() -> None:
    bad = dict(GOOD_PAYLOAD)
    extra: list[str] = list(GOOD_PAYLOAD["missing_things"])  # type: ignore[arg-type]
    extra.append("Extra")
    bad["missing_things"] = extra
    llm = FakeLLM(content=json.dumps(bad))
    assert (
        await generate_breakup_analysis(**_base_kwargs(), client=llm)  # type: ignore[arg-type]
    ) is None


async def test_generate_invalid_attachment_style_rejected() -> None:
    bad = dict(GOOD_PAYLOAD)
    bad_dyn = dict(GOOD_PAYLOAD["attachment_dynamics"])  # type: ignore[arg-type]
    bad_dyn["user"] = "made_up_style"
    bad["attachment_dynamics"] = bad_dyn
    llm = FakeLLM(content=json.dumps(bad))
    assert (
        await generate_breakup_analysis(**_base_kwargs(), client=llm)  # type: ignore[arg-type]
    ) is None


# ----- persist + end-to-end ------------------------------------------------


async def test_persist_writes_markdown_and_metadata() -> None:
    sb = FakeSupabase()
    sb.seed_host()

    result = BreakupAnalyzerResult(**GOOD_PAYLOAD)
    persisted = await persist_breakup_analyzer_run(
        sb,  # type: ignore[arg-type]
        user_id="u",
        run=BreakupAnalyzerRun(
            text_thread="thread",
            duration="2 years",
            user_age=29,
            partner_age=31,
            intent="end",
            result=result,
        ),
    )

    convo = sb.table("conversations").rows[0]
    assert convo["mode"] == "custom"
    assert convo["title"] == "Breakup analyzer"
    assert convo["metadata"]["tool"] == "breakup_analyzer"
    assert convo["metadata"]["intent"] == "end"
    assert convo["persona_id"] == "host-id"

    messages = sb.table("messages").rows
    assert len(messages) == 2
    body = messages[1]["content"]
    assert "## Attachment dynamics" in body
    assert "## Reconciliation likelihood: low" in body
    assert "## What you're missing" in body
    assert "## Suggested message (end)" in body

    meta = messages[1]["metadata"]
    assert meta["kind"] == "breakup_analysis"
    assert meta["attachment_dynamics"]["user"] == "anxious"
    assert len(meta["missing_things"]) == 3
    assert persisted.assistant_message_id == messages[1]["id"]


async def test_run_end_to_end_happy_path() -> None:
    sb = FakeSupabase()
    sb.seed_host()
    llm = FakeLLM(content=json.dumps(GOOD_PAYLOAD))

    run = await run_breakup_analyzer(
        sb,  # type: ignore[arg-type]
        user_id="u",
        text_thread="Real thread content here" + (" foo" * 20),
        duration="2 years",
        user_age=29,
        partner_age=31,
        intent="repair",
        client=llm,  # type: ignore[arg-type]
    )

    assert run is not None
    assert run.conversation_id is not None
    assert len(sb.table("messages").rows) == 2


async def test_run_llm_failure_yields_none_no_persistence() -> None:
    sb = FakeSupabase()
    sb.seed_host()
    llm = FakeLLM(exc=LiteLLMNetworkError("down"))

    run = await run_breakup_analyzer(
        sb,  # type: ignore[arg-type]
        user_id="u",
        text_thread="thread content" + (" foo" * 20),
        duration="2 years",
        user_age=29,
        partner_age=31,
        intent="repair",
        client=llm,  # type: ignore[arg-type]
    )
    assert run is None
    assert "conversations" not in sb.tables or sb.tables["conversations"].rows == []
