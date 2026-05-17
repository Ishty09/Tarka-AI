"""Mirror Mode generator tests.

Stubs the LLM and Supabase. Verifies the happy path, defensive empties on
LLM failure, tier gating, idempotency, and the JSON parse failure path.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.services.llm import LiteLLMError, LiteLLMNetworkError
from app.services.mirror import (
    MirrorReportPayload,
    generate_report,
    persist_report,
    run_for_user,
    run_weekly,
)


PERIOD_START = datetime(2026, 5, 10, tzinfo=UTC)
PERIOD_END = PERIOD_START + timedelta(days=7)


# ----- Fake LLM --------------------------------------------------------------


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


# ----- Fake Supabase ---------------------------------------------------------


class _Res:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, table: "_Table", op: str, payload: Any = None) -> None:
        self._table = table
        self._op = op
        self._payload = payload
        self._filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None
        self._on_conflict: str | None = None
        self._ignore_duplicates = False

    def select(self, _cols: str = "*") -> "_Query":
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, "eq", val))
        return self

    def gte(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, "gte", val))
        return self

    def lt(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, "lt", val))
        return self

    def in_(self, col: str, vals: list[Any]) -> "_Query":
        self._filters.append((col, "in", vals))
        return self

    def order(self, _col: str, desc: bool = False) -> "_Query":
        return self

    def limit(self, n: int) -> "_Query":
        self._limit = n
        return self

    def upsert_config(self, *, on_conflict: str, ignore_duplicates: bool) -> "_Query":
        self._on_conflict = on_conflict
        self._ignore_duplicates = ignore_duplicates
        return self

    async def execute(self) -> _Res:
        if self._op == "select":
            rows = list(self._table.rows)
            for col, op, val in self._filters:
                if op == "eq":
                    rows = [r for r in rows if r.get(col) == val]
                elif op == "gte":
                    rows = [r for r in rows if str(r.get(col, "")) >= str(val)]
                elif op == "lt":
                    rows = [r for r in rows if str(r.get(col, "")) < str(val)]
                elif op == "in":
                    rows = [r for r in rows if r.get(col) in val]
            if self._limit is not None:
                rows = rows[: self._limit]
            return _Res(rows)

        if self._op == "upsert":
            payload = self._payload if isinstance(self._payload, list) else [self._payload]
            inserted = []
            for row in payload:
                key_cols = self._on_conflict.split(",") if self._on_conflict else []
                match = None
                for r in self._table.rows:
                    if key_cols and all(r.get(k) == row.get(k) for k in key_cols):
                        match = r
                        break
                if match is None:
                    self._table.rows.append(dict(row))
                    inserted.append(row)
                elif not self._ignore_duplicates:
                    match.update(row)
                    inserted.append(match)
            return _Res(inserted)

        return _Res([])


class _Table:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, _cols: str = "*") -> _Query:
        return _Query(self, "select")

    def upsert(
        self,
        payload: Any,
        on_conflict: str | None = None,
        ignore_duplicates: bool = False,
    ) -> _Query:
        q = _Query(self, "upsert", payload)
        return q.upsert_config(
            on_conflict=on_conflict or "",
            ignore_duplicates=ignore_duplicates,
        )


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, _Table] = {}

    def table(self, name: str) -> _Table:
        if name not in self.tables:
            self.tables[name] = _Table(name)
        return self.tables[name]


def _seed_user(sb: FakeSupabase, user_id: str, *, tier: str, messages: list[str], facts: list[str]) -> None:
    sb.table("profiles").rows.append({"id": user_id, "tier": tier})
    inside = PERIOD_START + timedelta(days=1)
    for msg in messages:
        sb.table("messages").rows.append(
            {
                "user_id": user_id,
                "role": "user",
                "safety_verdict": "safe",
                "content": msg,
                "created_at": inside.isoformat(),
            }
        )
    for fact in facts:
        sb.table("user_facts").rows.append(
            {
                "user_id": user_id,
                "fact": fact,
                "created_at": inside.isoformat(),
            }
        )


# ----- generate_report -------------------------------------------------------


GOOD_PAYLOAD = {
    "summary": "You spent the week dodging the conversation with your manager.",
    "patterns": [
        {"theme": "Avoidance", "support": "Three turns reframed the question."},
    ],
    "dodges": [
        {"topic": "Salary conversation", "observed": "Never asked, kept hedging."},
    ],
}


async def test_generate_report_parses_well_formed_output() -> None:
    llm = FakeLLM(content=json.dumps(GOOD_PAYLOAD))
    payload = await generate_report(
        user_messages=["msg1", "msg2"],
        facts=["fact1"],
        client=llm,  # type: ignore[arg-type]
    )
    assert payload is not None
    assert payload.summary.startswith("You spent")
    assert len(payload.patterns) == 1
    assert payload.patterns[0].theme == "Avoidance"


async def test_generate_report_empty_inputs_short_circuit() -> None:
    llm = FakeLLM(content="should not be called")
    payload = await generate_report(user_messages=[], facts=[], client=llm)  # type: ignore[arg-type]
    assert payload is None
    assert llm.calls == []


async def test_generate_report_llm_error_returns_none() -> None:
    llm = FakeLLM(exc=LiteLLMNetworkError("down"))
    payload = await generate_report(user_messages=["x"], facts=[], client=llm)  # type: ignore[arg-type]
    assert payload is None


async def test_generate_report_http_error_returns_none() -> None:
    llm = FakeLLM(exc=LiteLLMError("500", 500, "x"))
    payload = await generate_report(user_messages=["x"], facts=[], client=llm)  # type: ignore[arg-type]
    assert payload is None


async def test_generate_report_malformed_json_returns_none() -> None:
    llm = FakeLLM(content="not json")
    payload = await generate_report(user_messages=["x"], facts=[], client=llm)  # type: ignore[arg-type]
    assert payload is None


async def test_generate_report_schema_violation_returns_none() -> None:
    # Pattern over the 5-item max
    bad = {
        "summary": "ok",
        "patterns": [{"theme": "x", "support": "y"} for _ in range(6)],
        "dodges": [],
    }
    llm = FakeLLM(content=json.dumps(bad))
    payload = await generate_report(user_messages=["x"], facts=[], client=llm)  # type: ignore[arg-type]
    assert payload is None


# ----- persist_report -------------------------------------------------------


async def test_persist_idempotent_on_same_window() -> None:
    sb = FakeSupabase()
    payload = MirrorReportPayload(**GOOD_PAYLOAD)
    first = await persist_report(
        sb,  # type: ignore[arg-type]
        user_id="u",
        period_start=PERIOD_START.date(),
        period_end=PERIOD_END.date(),
        payload=payload,
    )
    second = await persist_report(
        sb,  # type: ignore[arg-type]
        user_id="u",
        period_start=PERIOD_START.date(),
        period_end=PERIOD_END.date(),
        payload=payload,
    )
    assert first is True
    assert second is False
    assert len(sb.table("mirror_reports").rows) == 1


# ----- run_for_user --------------------------------------------------------


async def test_run_for_user_skips_when_no_messages_in_window() -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.append({"id": "u", "tier": "pro"})
    llm = FakeLLM(content=json.dumps(GOOD_PAYLOAD))
    result = await run_for_user(
        sb,  # type: ignore[arg-type]
        user_id="u",
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        client=llm,  # type: ignore[arg-type]
    )
    assert result.inserted is False
    assert result.reason == "no_messages"
    assert llm.calls == []


async def test_run_for_user_inserts_on_happy_path() -> None:
    sb = FakeSupabase()
    _seed_user(sb, "u", tier="pro", messages=["m1", "m2"], facts=["f1"])
    llm = FakeLLM(content=json.dumps(GOOD_PAYLOAD))
    result = await run_for_user(
        sb,  # type: ignore[arg-type]
        user_id="u",
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        client=llm,  # type: ignore[arg-type]
    )
    assert result.inserted is True
    rows = sb.table("mirror_reports").rows
    assert len(rows) == 1
    assert rows[0]["summary"].startswith("You spent")
    # patterns and dodges land as plain dicts (jsonb-friendly).
    assert rows[0]["patterns"][0]["theme"] == "Avoidance"


# ----- run_weekly tier gating ----------------------------------------------


async def test_run_weekly_skips_free_tier_users() -> None:
    sb = FakeSupabase()
    _seed_user(sb, "free-user", tier="free", messages=["m1"], facts=[])
    _seed_user(sb, "pro-user", tier="pro", messages=["m2"], facts=[])
    llm = FakeLLM(content=json.dumps(GOOD_PAYLOAD))
    result = await run_weekly(
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        client=llm,  # type: ignore[arg-type]
        supabase=sb,  # type: ignore[arg-type]
    )
    assert result == {"eligible_users": 1, "inserted": 1, "skipped": 0}
    rows = sb.table("mirror_reports").rows
    assert len(rows) == 1
    assert rows[0]["user_id"] == "pro-user"


async def test_run_weekly_handles_no_eligible_users() -> None:
    sb = FakeSupabase()
    llm = FakeLLM(content=json.dumps(GOOD_PAYLOAD))
    result = await run_weekly(
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        client=llm,  # type: ignore[arg-type]
        supabase=sb,  # type: ignore[arg-type]
    )
    assert result == {"eligible_users": 0, "inserted": 0, "skipped": 0}
    assert llm.calls == []
