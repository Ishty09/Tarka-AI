"""Wager evaluator tests.

Stubs LLM + Supabase. Covers verdict parsing, defensive failure paths,
referee-skip, persistence guard against double-evaluation, and the
batch orchestration.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

os.environ.setdefault("NEXT_PUBLIC_APP_URL", "https://quarrel.test")
os.environ.setdefault("LITELLM_PROXY_URL", "https://litellm.test")
os.environ.setdefault("LITELLM_MASTER_KEY", "test")
os.environ.setdefault("NEXT_PUBLIC_SUPABASE_URL", "https://supabase.test")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test")
os.environ.setdefault("NEXT_PUBLIC_SUPABASE_ANON_KEY", "test")

from app.services import wager_evaluator as we_mod
from app.services.llm import LiteLLMError, LiteLLMNetworkError
from app.services.wager_evaluator import (
    EvaluatorVerdict,
    _format_stake,
    _format_stake_amount_only,
    _notify_outcome,
    evaluate_wager,
    generate_verdict,
    persist_verdict,
    run_due_evaluations,
)


GOOD_VERDICT = {
    "outcome": "succeeded",
    "reasoning": "10 of 14 days completed; notes are concrete and back the status.",
}


# ----- Fakes ---------------------------------------------------------------


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
        self._filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None
        self._maybe_single = False

    def select(self, _cols: str = "*") -> "_Query":
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, "eq", val))
        return self

    def lte(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, "lte", val))
        return self

    def order(self, _col: str, desc: bool = False) -> "_Query":
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
            for col, op, val in self._filters:
                if op == "eq":
                    rows = [r for r in rows if r.get(col) == val]
                elif op == "lte":
                    rows = [r for r in rows if str(r.get(col, "")) <= str(val)]
            if self._limit is not None:
                rows = rows[: self._limit]
            if self._maybe_single:
                return _Res(rows[0] if rows else None)
            return _Res(rows)

        if self._op == "update":
            for row in self._table.rows:
                if all(r := True for _ in ()):
                    pass
                if all(
                    (
                        op == "eq"
                        and row.get(col) == val
                    )
                    for col, op, val in self._filters
                ):
                    row.update(self._payload)
            return _Res([])

        return _Res([])


class _Table:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, _cols: str = "*") -> _Query:
        return _Query(self, "select")

    def update(self, payload: Any) -> _Query:
        return _Query(self, "update", payload)


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, _Table] = {}

    def table(self, name: str) -> _Table:
        if name not in self.tables:
            self.tables[name] = _Table(name)
        return self.tables[name]


def _wager(
    *,
    wager_id: str = "w-1",
    user_id: str = "u",
    status: str = "active",
    referee_id: str | None = None,
    end_at: str = "2026-05-19",
    start_at: str = "2026-05-12",
) -> dict[str, Any]:
    return {
        "id": wager_id,
        "user_id": user_id,
        "goal": "Run 4x/week.",
        "stake_cents": 5000,
        "currency": "usd",
        "anti_charity_slug": "heritage-foundation",
        "start_at": start_at,
        "end_at": end_at,
        "status": status,
        "referee_id": referee_id,
    }


# ----- generate_verdict -----------------------------------------------------


async def test_generate_verdict_well_formed() -> None:
    llm = FakeLLM(content=json.dumps(GOOD_VERDICT))
    verdict = await generate_verdict(
        wager=_wager(),
        checkins=[],
        aggregate={"total_days": 7, "completed": 6, "missed": 1, "skipped": 0, "unfilled": 0},
        client=llm,  # type: ignore[arg-type]
    )
    assert verdict == EvaluatorVerdict(**GOOD_VERDICT)


async def test_generate_verdict_network_error_returns_none() -> None:
    llm = FakeLLM(exc=LiteLLMNetworkError("down"))
    assert (
        await generate_verdict(
            wager=_wager(),
            checkins=[],
            aggregate={"total_days": 7, "completed": 0, "missed": 0, "skipped": 0, "unfilled": 7},
            client=llm,  # type: ignore[arg-type]
        )
    ) is None


async def test_generate_verdict_http_error_returns_none() -> None:
    llm = FakeLLM(exc=LiteLLMError("500", 500, "x"))
    assert (
        await generate_verdict(
            wager=_wager(),
            checkins=[],
            aggregate={"total_days": 7, "completed": 0, "missed": 0, "skipped": 0, "unfilled": 7},
            client=llm,  # type: ignore[arg-type]
        )
    ) is None


async def test_generate_verdict_malformed_json_returns_none() -> None:
    llm = FakeLLM(content="not json")
    assert (
        await generate_verdict(
            wager=_wager(),
            checkins=[],
            aggregate={"total_days": 7, "completed": 0, "missed": 0, "skipped": 0, "unfilled": 7},
            client=llm,  # type: ignore[arg-type]
        )
    ) is None


async def test_generate_verdict_invalid_outcome_enum_rejected() -> None:
    bad = {"outcome": "won_lol", "reasoning": "10/14 days hit"}
    llm = FakeLLM(content=json.dumps(bad))
    assert (
        await generate_verdict(
            wager=_wager(),
            checkins=[],
            aggregate={"total_days": 14, "completed": 10, "missed": 4, "skipped": 0, "unfilled": 0},
            client=llm,  # type: ignore[arg-type]
        )
    ) is None


# ----- persist_verdict ------------------------------------------------------


async def test_persist_only_updates_active_rows() -> None:
    sb = FakeSupabase()
    sb.table("wagers").rows.extend([
        {"id": "w-1", "status": "active", "evaluation_notes": None},
        {"id": "w-2", "status": "succeeded", "evaluation_notes": None},
    ])
    await persist_verdict(
        sb,  # type: ignore[arg-type]
        wager_id="w-1",
        outcome="failed",
        reasoning="not enough.",
    )
    # w-1 should flip; w-2 should be untouched because the filter requires status='active'.
    rows = {r["id"]: r for r in sb.table("wagers").rows}
    assert rows["w-1"]["status"] == "failed"
    assert rows["w-1"]["evaluation_notes"] == "not enough."
    assert rows["w-2"]["status"] == "succeeded"
    assert rows["w-2"]["evaluation_notes"] is None


# ----- evaluate_wager ------------------------------------------------------


async def _seed_wager_with_checkins(sb: FakeSupabase, *, end_at: str, statuses: list[str]) -> None:
    wager = _wager(end_at=end_at, start_at="2026-05-12")
    sb.table("wagers").rows.append(wager)
    start = date.fromisoformat("2026-05-12")
    for i, s in enumerate(statuses):
        sb.table("wager_checkins").rows.append(
            {
                "wager_id": wager["id"],
                "checkin_date": (start + timedelta(days=i)).isoformat(),
                "status": s,
                "notes": None,
                "proof_url": None,
            }
        )


async def test_evaluate_wager_referee_skips() -> None:
    sb = FakeSupabase()
    sb.table("wagers").rows.append(_wager(referee_id="ref-1"))
    result = await evaluate_wager(
        sb,  # type: ignore[arg-type]
        wager=sb.table("wagers").rows[0],
        client=FakeLLM(content=json.dumps(GOOD_VERDICT)),  # type: ignore[arg-type]
    )
    assert result is None


async def test_evaluate_wager_happy_path_persists() -> None:
    sb = FakeSupabase()
    await _seed_wager_with_checkins(
        sb,
        end_at="2026-05-19",
        statuses=["completed"] * 6 + ["missed"],
    )
    llm = FakeLLM(content=json.dumps(GOOD_VERDICT))
    result = await evaluate_wager(
        sb,  # type: ignore[arg-type]
        wager=sb.table("wagers").rows[0],
        client=llm,  # type: ignore[arg-type]
    )
    assert result is not None
    assert result.outcome == "succeeded"
    assert "completed" in result.reasoning.lower() or "10" in result.reasoning
    row = sb.table("wagers").rows[0]
    assert row["status"] == "succeeded"
    assert row["evaluation_notes"]


async def test_evaluate_wager_llm_failure_no_persist() -> None:
    sb = FakeSupabase()
    await _seed_wager_with_checkins(sb, end_at="2026-05-19", statuses=["missed"] * 7)
    llm = FakeLLM(exc=LiteLLMNetworkError("down"))
    result = await evaluate_wager(
        sb,  # type: ignore[arg-type]
        wager=sb.table("wagers").rows[0],
        client=llm,  # type: ignore[arg-type]
    )
    assert result is None
    assert sb.table("wagers").rows[0]["status"] == "active"


# ----- run_due_evaluations -------------------------------------------------


async def test_run_due_finds_only_active_with_end_at_passed() -> None:
    sb = FakeSupabase()
    sb.table("wagers").rows.extend([
        _wager(wager_id="due-active", status="active", end_at="2026-05-10"),
        _wager(wager_id="future-active", status="active", end_at="2026-06-10"),
        _wager(wager_id="due-succeeded", status="succeeded", end_at="2026-05-10"),
    ])
    # Seed a few checkins so the LLM call has signal (any content works).
    sb.table("wager_checkins").rows.append(
        {
            "wager_id": "due-active",
            "checkin_date": "2026-05-09",
            "status": "completed",
            "notes": None,
            "proof_url": None,
        }
    )

    llm = FakeLLM(content=json.dumps(GOOD_VERDICT))
    result = await run_due_evaluations(
        cutoff_date=date.fromisoformat("2026-05-19"),
        client=llm,  # type: ignore[arg-type]
        supabase=sb,  # type: ignore[arg-type]
    )

    # One due active wager — gets evaluated. The succeeded row doesn't,
    # and the future-end-at one is filtered by the .lte.
    assert result["candidates"] == 1
    assert result["succeeded"] == 1
    assert result["failed"] == 0
    rows = {r["id"]: r for r in sb.table("wagers").rows}
    assert rows["due-active"]["status"] == "succeeded"
    assert rows["future-active"]["status"] == "active"
    assert rows["due-succeeded"]["status"] == "succeeded"  # untouched


# ----- Stake formatting ----------------------------------------------------


def test_format_stake_two_decimal_dollars() -> None:
    assert _format_stake(5000) == "$50.00"
    assert _format_stake(100_000) == "$1,000.00"
    assert _format_stake(1234) == "$12.34"
    assert _format_stake(0) == "$0.00"
    assert _format_stake(None) == "$0.00"
    assert _format_stake(-1) == "$0.00"


def test_format_stake_amount_only_strips_dollar_sign() -> None:
    """${stake} push body has a literal '$' already; helper returns just
    the number so we don't end up rendering '$$50.00'.
    """

    assert _format_stake_amount_only(5000) == "50.00"
    assert _format_stake_amount_only(100_000) == "1,000.00"


# ----- _notify_outcome -----------------------------------------------------


async def test_notify_outcome_failed_fires_push_and_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed verdict must fire BOTH the wager_failed push (so the
    user finds out off-app) AND the wager_lost email (so they have a
    receipt for the anti-charity donation).
    """

    sb = FakeSupabase()
    sb.table("anti_charities").rows.append(
        {"slug": "heritage-foundation", "name": "Heritage Foundation"}
    )

    push_calls: list[dict[str, Any]] = []
    email_calls: list[dict[str, Any]] = []

    async def fake_push(**kwargs: Any) -> list[Any]:
        push_calls.append(kwargs)
        return [type("R", (), {"status": "sent"})()]

    async def fake_email(**kwargs: Any) -> Any:
        email_calls.append(kwargs)
        return type("R", (), {"status": "sent"})()

    async def fake_resolve_email(_sb: Any, *, user_id: str) -> str:
        return f"{user_id}@example.test"

    monkeypatch.setattr(we_mod, "deliver_to_user", fake_push)
    monkeypatch.setattr(we_mod, "send_email", fake_email)
    monkeypatch.setattr(we_mod, "_resolve_email", fake_resolve_email)

    await _notify_outcome(
        sb,  # type: ignore[arg-type]
        wager=_wager(wager_id="w-fail"),
        outcome="failed",
    )

    # Push: wager_failed template, with the anti-charity's HUMAN name
    # (not the slug) and the stake amount without a leading "$".
    assert len(push_calls) == 1
    pcall = push_calls[0]
    assert pcall["template"] == "wager_failed"
    assert pcall["variables"] == {
        "stake": "50.00",
        "anti_charity": "Heritage Foundation",
    }
    assert pcall["idempotency_key"] == "push:wager_failed:w-fail"
    assert "/wagers/w-fail" in pcall["deep_link"]

    # Email: wager_lost template, with stake_formatted (the leading "$"
    # version) and the resolved charity name.
    assert len(email_calls) == 1
    ecall = email_calls[0]
    assert ecall["template"] == "wager_lost"
    assert ecall["variables"]["stake_formatted"] == "$50.00"
    assert ecall["variables"]["anti_charity_name"] == "Heritage Foundation"
    assert ecall["variables"]["goal"] == "Run 4x/week."
    assert ecall["variables"]["wager_id"] == "w-fail"
    assert ecall["idempotency_key"] == "email:wager_lost:w-fail"


async def test_notify_outcome_succeeded_fires_email_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A succeeded verdict fires only the wager_won email — there's no
    wager_won push template (§13 deliberately doesn't register one).
    """

    sb = FakeSupabase()
    push_calls: list[dict[str, Any]] = []
    email_calls: list[dict[str, Any]] = []

    async def fake_push(**kwargs: Any) -> list[Any]:
        push_calls.append(kwargs)
        return []

    async def fake_email(**kwargs: Any) -> Any:
        email_calls.append(kwargs)
        return type("R", (), {"status": "sent"})()

    async def fake_resolve_email(_sb: Any, *, user_id: str) -> str:
        return f"{user_id}@example.test"

    monkeypatch.setattr(we_mod, "deliver_to_user", fake_push)
    monkeypatch.setattr(we_mod, "send_email", fake_email)
    monkeypatch.setattr(we_mod, "_resolve_email", fake_resolve_email)

    await _notify_outcome(
        sb,  # type: ignore[arg-type]
        wager=_wager(wager_id="w-win"),
        outcome="succeeded",
    )

    assert push_calls == []
    assert len(email_calls) == 1
    ecall = email_calls[0]
    assert ecall["template"] == "wager_won"
    assert "anti_charity_name" not in ecall["variables"]
    assert ecall["idempotency_key"] == "email:wager_won:w-win"


async def test_notify_outcome_swallows_email_lookup_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User without an auth email row (e.g. social-login that omits it)
    should still get the push but skip the email cleanly — no crash.
    """

    sb = FakeSupabase()
    sb.table("anti_charities").rows.append(
        {"slug": "heritage-foundation", "name": "Heritage Foundation"}
    )

    push_calls: list[dict[str, Any]] = []
    email_calls: list[dict[str, Any]] = []

    async def fake_push(**kwargs: Any) -> list[Any]:
        push_calls.append(kwargs)
        return [type("R", (), {"status": "sent"})()]

    async def fake_email(**kwargs: Any) -> Any:
        email_calls.append(kwargs)
        return type("R", (), {"status": "sent"})()

    async def no_email(_sb: Any, *, user_id: str) -> str | None:
        return None

    monkeypatch.setattr(we_mod, "deliver_to_user", fake_push)
    monkeypatch.setattr(we_mod, "send_email", fake_email)
    monkeypatch.setattr(we_mod, "_resolve_email", no_email)

    await _notify_outcome(
        sb,  # type: ignore[arg-type]
        wager=_wager(),
        outcome="failed",
    )

    assert len(push_calls) == 1
    assert email_calls == []


async def test_evaluate_wager_invokes_notify(monkeypatch: pytest.MonkeyPatch) -> None:
    """Integration check — evaluate_wager's happy path actually calls
    _notify_outcome with the verdict outcome.
    """

    sb = FakeSupabase()
    sb.table("wagers").rows.append(_wager(wager_id="w-int"))
    notify_calls: list[dict[str, Any]] = []

    async def fake_notify(_sb: Any, *, wager: dict[str, Any], outcome: str) -> None:
        notify_calls.append({"wager_id": wager["id"], "outcome": outcome})

    monkeypatch.setattr(we_mod, "_notify_outcome", fake_notify)

    llm = FakeLLM(content=json.dumps(GOOD_VERDICT))
    out = await evaluate_wager(
        sb,  # type: ignore[arg-type]
        wager=sb.table("wagers").rows[0],
        client=llm,  # type: ignore[arg-type]
    )
    assert out is not None and out.outcome == "succeeded"
    assert notify_calls == [{"wager_id": "w-int", "outcome": "succeeded"}]
