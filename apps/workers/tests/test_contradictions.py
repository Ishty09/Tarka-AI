"""Contradiction service tests.

Stubs the LLM and Supabase. The job's orchestration is tested via
run_for_user end-to-end so we can verify the new-fact → candidate →
LLM-judge → insert flow.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

os.environ.setdefault("NEXT_PUBLIC_APP_URL", "https://quarrel.test")
os.environ.setdefault("LITELLM_PROXY_URL", "https://litellm.test")
os.environ.setdefault("LITELLM_MASTER_KEY", "test")
os.environ.setdefault("NEXT_PUBLIC_SUPABASE_URL", "https://supabase.test")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test")
os.environ.setdefault("NEXT_PUBLIC_SUPABASE_ANON_KEY", "test")

from app.services import contradictions as contradictions_mod
from app.services.contradictions import (
    DEFAULT_SEVERITY_THRESHOLD,
    ContradictionJudgment,
    insert_contradiction,
    judge_pair,
    run_for_user,
)
from app.services.llm import LiteLLMError, LiteLLMNetworkError


# ----- Fake LLM --------------------------------------------------------------


class FakeLLM:
    def __init__(self, responses: list[Any] | None = None) -> None:
        """responses can mix dict payloads (returned as JSON) and exceptions."""

        self.responses = list(responses or [])
        self.calls: list[dict[str, Any]] = []

    async def chat(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if not self.responses:
            raise RuntimeError("no canned response left")
        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return {
            "choices": [{"message": {"role": "assistant", "content": json.dumps(nxt)}}],
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

    @property
    def not_(self) -> "_NotProxy":
        return _NotProxy(self)

    async def execute(self) -> _Res:
        if self._op == "select":
            rows = list(self._table.rows)
            for col, op, val in self._filters:
                if op == "eq":
                    rows = [r for r in rows if r.get(col) == val]
                elif op == "gte":
                    rows = [r for r in rows if str(r.get(col, "")) >= str(val)]
                elif op == "not_null":
                    rows = [r for r in rows if r.get(col) is not None]
            return _Res(rows)

        if self._op == "insert":
            payload = self._payload if isinstance(self._payload, list) else [self._payload]
            inserted = []
            for row in payload:
                new_row = dict(row)
                if "id" not in new_row:
                    new_row["id"] = len(self._table.rows) + 1
                self._table.rows.append(new_row)
                inserted.append(new_row)
            return _Res(inserted)

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
                    new_row = dict(row)
                    if "id" not in new_row:
                        new_row["id"] = len(self._table.rows) + 1
                    self._table.rows.append(new_row)
                    inserted.append(new_row)
                elif not self._ignore_duplicates:
                    match.update(row)
                    inserted.append(match)
            return _Res(inserted)

        return _Res([])

    def upsert_config(self, *, on_conflict: str, ignore_duplicates: bool) -> "_Query":
        self._on_conflict = on_conflict
        self._ignore_duplicates = ignore_duplicates
        return self


class _NotProxy:
    def __init__(self, parent: _Query) -> None:
        self._parent = parent

    def is_(self, col: str, val: Any) -> _Query:
        # We only handle "not is null" — anything else is a no-op filter.
        if val == "null":
            self._parent._filters.append((col, "not_null", None))
        return self._parent


class _Table:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, _cols: str = "*") -> _Query:
        return _Query(self, "select")

    def insert(self, payload: Any) -> _Query:
        return _Query(self, "insert", payload)

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


class _RpcQuery:
    def __init__(self, parent: "FakeSupabase", name: str, params: dict[str, Any]) -> None:
        self._parent = parent
        self._name = name
        self._params = params

    async def execute(self) -> _Res:
        self._parent.rpc_calls.append({"name": self._name, "params": self._params})
        return _Res(self._parent.rpc_results.get(self._name, []))


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, _Table] = {}
        self.rpc_results: dict[str, list[dict[str, Any]]] = {}
        self.rpc_calls: list[dict[str, Any]] = []

    def table(self, name: str) -> _Table:
        if name not in self.tables:
            self.tables[name] = _Table(name)
        return self.tables[name]

    def rpc(self, name: str, params: dict[str, Any] | None = None) -> _RpcQuery:
        return _RpcQuery(self, name, params or {})


# ----- judge_pair -----------------------------------------------------------


async def test_judge_pair_parses_well_formed_output() -> None:
    llm = FakeLLM(
        responses=[
            {
                "is_contradiction": True,
                "severity": 8,
                "summary": "You said X then Y.",
            }
        ]
    )
    result = await judge_pair("Fact A", "Fact B", client=llm)  # type: ignore[arg-type]
    assert result == ContradictionJudgment(
        is_contradiction=True, severity=8, summary="You said X then Y."
    )


async def test_judge_pair_llm_error_returns_none() -> None:
    llm = FakeLLM(responses=[LiteLLMNetworkError("down")])
    assert await judge_pair("a", "b", client=llm) is None  # type: ignore[arg-type]


async def test_judge_pair_http_error_returns_none() -> None:
    llm = FakeLLM(responses=[LiteLLMError("500", 500, "x")])
    assert await judge_pair("a", "b", client=llm) is None  # type: ignore[arg-type]


async def test_judge_pair_malformed_json_returns_none() -> None:
    # FakeLLM serialises dict to JSON; to force malformed output we hand-roll.
    class BadLLM:
        async def chat(self, **kwargs: Any) -> dict[str, Any]:
            return {"choices": [{"message": {"role": "assistant", "content": "not json"}}]}

    assert await judge_pair("a", "b", client=BadLLM()) is None  # type: ignore[arg-type]


async def test_judge_pair_severity_out_of_range_returns_none() -> None:
    llm = FakeLLM(
        responses=[{"is_contradiction": True, "severity": 99, "summary": "x"}]
    )
    assert await judge_pair("a", "b", client=llm) is None  # type: ignore[arg-type]


# ----- insert_contradiction -------------------------------------------------


async def test_insert_canonicalises_pair_ordering() -> None:
    sb = FakeSupabase()
    inserted = await insert_contradiction(
        sb,  # type: ignore[arg-type]
        user_id="u",
        fact_a_id=99,
        fact_b_id=10,
        severity=7,
        summary="conflict",
    )
    assert inserted is True
    rows = sb.table("contradictions").rows
    assert len(rows) == 1
    assert rows[0]["fact_a_id"] == 10  # min
    assert rows[0]["fact_b_id"] == 99  # max


async def test_insert_duplicate_pair_is_skipped() -> None:
    sb = FakeSupabase()
    first = await insert_contradiction(
        sb,  # type: ignore[arg-type]
        user_id="u",
        fact_a_id=1,
        fact_b_id=2,
        severity=5,
        summary="a",
    )
    second = await insert_contradiction(
        sb,  # type: ignore[arg-type]
        user_id="u",
        fact_a_id=2,
        fact_b_id=1,  # reversed — canonicalises to same pair
        severity=6,
        summary="b",
    )
    assert first is True
    assert second is False
    assert len(sb.table("contradictions").rows) == 1


# ----- run_for_user ---------------------------------------------------------


async def test_run_for_user_judges_candidates_and_inserts_threshold_hits() -> None:
    sb = FakeSupabase()
    since = datetime.now(UTC) - timedelta(hours=24)
    later = (since + timedelta(hours=1)).isoformat()

    # One brand-new fact, with an embedding so it's eligible.
    sb.table("user_facts").rows.append(
        {
            "id": 100,
            "user_id": "u",
            "fact": "User said quitting is overrated.",
            "embedding": [0.1] * 1536,
            "is_active": True,
            "created_at": later,
        }
    )
    # Two candidate matches from match_user_facts — one above threshold,
    # one below.
    sb.rpc_results["match_user_facts"] = [
        {"id": 100, "fact": "self — should be filtered out"},  # same id excluded
        {"id": 50, "fact": "User committed to quitting by Friday."},
        {"id": 30, "fact": "User likes coffee."},
    ]

    llm = FakeLLM(
        responses=[
            # First candidate (id=50) — strong contradiction
            {
                "is_contradiction": True,
                "severity": DEFAULT_SEVERITY_THRESHOLD + 2,
                "summary": "You said you'd quit, now you say quitting is overrated.",
            },
            # Second candidate (id=30) — unrelated
            {
                "is_contradiction": False,
                "severity": 0,
                "summary": "No conflict detected.",
            },
        ]
    )

    result = await run_for_user(
        sb,  # type: ignore[arg-type]
        user_id="u",
        since=since,
        client=llm,  # type: ignore[arg-type]
    )

    assert result["new_facts"] == 1
    assert result["pairs_judged"] == 2  # candidate id=100 was excluded client-side
    assert result["contradictions_inserted"] == 1

    rows = sb.table("contradictions").rows
    assert len(rows) == 1
    assert sorted([rows[0]["fact_a_id"], rows[0]["fact_b_id"]]) == [50, 100]
    assert rows[0]["severity"] == DEFAULT_SEVERITY_THRESHOLD + 2


async def test_run_for_user_below_threshold_no_insert() -> None:
    sb = FakeSupabase()
    since = datetime.now(UTC) - timedelta(hours=24)
    later = (since + timedelta(hours=1)).isoformat()

    sb.table("user_facts").rows.append(
        {
            "id": 1,
            "user_id": "u",
            "fact": "User said A.",
            "embedding": [0.1] * 1536,
            "is_active": True,
            "created_at": later,
        }
    )
    sb.rpc_results["match_user_facts"] = [{"id": 2, "fact": "User said B."}]

    llm = FakeLLM(
        responses=[
            {
                "is_contradiction": True,
                "severity": DEFAULT_SEVERITY_THRESHOLD - 1,
                "summary": "mild tension",
            }
        ]
    )
    result = await run_for_user(sb, user_id="u", since=since, client=llm)  # type: ignore[arg-type]
    assert result["contradictions_inserted"] == 0
    assert sb.table("contradictions").rows == []


async def test_run_for_user_skips_facts_without_embedding() -> None:
    sb = FakeSupabase()
    since = datetime.now(UTC) - timedelta(hours=24)
    later = (since + timedelta(hours=1)).isoformat()

    sb.table("user_facts").rows.append(
        {
            "id": 1,
            "user_id": "u",
            "fact": "User said A.",
            "embedding": None,  # not yet embedded — skip
            "is_active": True,
            "created_at": later,
        }
    )
    llm = FakeLLM()  # no responses prepared — must not be called
    result = await run_for_user(sb, user_id="u", since=since, client=llm)  # type: ignore[arg-type]
    assert result == {"new_facts": 0, "pairs_judged": 0, "contradictions_inserted": 0}
    assert llm.calls == []


# ----- Push fire ----------------------------------------------------------


async def test_run_for_user_fires_one_push_with_top_severity_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If multiple contradictions clear the threshold in a single run,
    fire exactly ONE push and use the HIGHEST-severity summary so the
    user sees the most actionable one. Click-through to the Wall shows
    them all anyway.
    """

    sb = FakeSupabase()
    since = datetime.now(UTC) - timedelta(hours=24)
    later = (since + timedelta(hours=1)).isoformat()

    # Two new facts; each will get one candidate match. First insert is
    # mild, second is severe — the push body should carry the severe one.
    sb.table("user_facts").rows.extend(
        [
            {
                "id": 100,
                "user_id": "u",
                "fact": "fact one",
                "embedding": [0.1] * 1536,
                "is_active": True,
                "created_at": later,
            },
            {
                "id": 101,
                "user_id": "u",
                "fact": "fact two",
                "embedding": [0.1] * 1536,
                "is_active": True,
                "created_at": later,
            },
        ]
    )
    sb.rpc_results["match_user_facts"] = [
        {"id": 50, "fact": "candidate"},
    ]

    llm = FakeLLM(
        responses=[
            {
                "is_contradiction": True,
                "severity": DEFAULT_SEVERITY_THRESHOLD,
                "summary": "Mild — barely above the bar.",
            },
            {
                "is_contradiction": True,
                "severity": DEFAULT_SEVERITY_THRESHOLD + 3,
                "summary": "Severe — this is the one to surface.",
            },
        ]
    )

    push_calls: list[dict[str, Any]] = []

    async def fake_push(**kwargs: Any) -> list[Any]:
        push_calls.append(kwargs)
        return [type("R", (), {"status": "sent"})()]

    monkeypatch.setattr(contradictions_mod, "deliver_to_user", fake_push)

    result = await run_for_user(sb, user_id="u", since=since, client=llm)  # type: ignore[arg-type]
    assert result["contradictions_inserted"] == 2

    assert len(push_calls) == 1
    call = push_calls[0]
    assert call["template"] == "contradiction"
    assert call["variables"] == {"summary": "Severe — this is the one to surface."}
    # Key shape includes user_id + since's date so a same-day retry
    # dedupes but tomorrow's batch fires fresh.
    assert call["idempotency_key"].startswith("push:contradiction:u:")


async def test_run_for_user_no_inserts_means_no_push(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When all candidates fall below the threshold (or aren't real
    contradictions), no push fires. The user shouldn't get pinged for
    a quiet batch.
    """

    sb = FakeSupabase()
    since = datetime.now(UTC) - timedelta(hours=24)
    later = (since + timedelta(hours=1)).isoformat()
    sb.table("user_facts").rows.append(
        {
            "id": 1,
            "user_id": "u",
            "fact": "fact",
            "embedding": [0.1] * 1536,
            "is_active": True,
            "created_at": later,
        }
    )
    sb.rpc_results["match_user_facts"] = [{"id": 2, "fact": "candidate"}]
    llm = FakeLLM(
        responses=[
            {
                "is_contradiction": True,
                "severity": DEFAULT_SEVERITY_THRESHOLD - 1,
                "summary": "below threshold",
            }
        ]
    )

    push_calls: list[dict[str, Any]] = []

    async def fake_push(**kwargs: Any) -> list[Any]:
        push_calls.append(kwargs)
        return []

    monkeypatch.setattr(contradictions_mod, "deliver_to_user", fake_push)

    await run_for_user(sb, user_id="u", since=since, client=llm)  # type: ignore[arg-type]
    assert push_calls == []
