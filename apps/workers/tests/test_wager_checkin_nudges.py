"""Daily wager check-in nudge."""

from __future__ import annotations

import os
from datetime import date
from typing import Any

import pytest

os.environ.setdefault("NEXT_PUBLIC_APP_URL", "https://quarrel.test")
os.environ.setdefault("LITELLM_PROXY_URL", "https://litellm.test")
os.environ.setdefault("LITELLM_MASTER_KEY", "test")
os.environ.setdefault("NEXT_PUBLIC_SUPABASE_URL", "https://supabase.test")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test")
os.environ.setdefault("NEXT_PUBLIC_SUPABASE_ANON_KEY", "test")

from app.services import wager_checkin_nudges as nudges_mod
from app.services.wager_checkin_nudges import (
    _format_stake,
    _short_goal,
    run_nudges,
)


# ----- Fake supabase -------------------------------------------------------


class _Res:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, table: "_Table", op: str = "select") -> None:
        self._table = table
        self._op = op
        self._filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None

    def select(self, _cols: str = "*") -> "_Query":
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, "eq", val))
        return self

    def lte(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, "lte", val))
        return self

    def gte(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, "gte", val))
        return self

    def limit(self, n: int) -> "_Query":
        self._limit = n
        return self

    async def execute(self) -> _Res:
        rows = list(self._table.rows)
        for col, op, val in self._filters:
            if op == "eq":
                rows = [r for r in rows if r.get(col) == val]
            elif op == "lte":
                rows = [r for r in rows if r.get(col) is not None and r.get(col) <= val]
            elif op == "gte":
                rows = [r for r in rows if r.get(col) is not None and r.get(col) >= val]
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Res(rows)


class _Table:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, _cols: str = "*") -> _Query:
        return _Query(self)


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, _Table] = {}

    def table(self, name: str) -> _Table:
        if name not in self.tables:
            self.tables[name] = _Table(name)
        return self.tables[name]


# ----- Helpers -------------------------------------------------------------


def test_short_goal_truncates_long_text() -> None:
    long = "x" * 200
    out = _short_goal(long, max_len=60)
    assert len(out) == 60
    assert out.endswith("…")


def test_short_goal_passes_short_text_through() -> None:
    assert _short_goal("Lift 3x/wk", max_len=60) == "Lift 3x/wk"


def test_short_goal_handles_none() -> None:
    assert _short_goal(None) == "(your goal)"


def test_format_stake_returns_whole_dollar_string() -> None:
    assert _format_stake(5000) == "50"
    assert _format_stake(100_000) == "1,000"
    assert _format_stake(0) == "0"
    assert _format_stake(None) == "0"


# ----- run_nudges ----------------------------------------------------------


async def test_run_nudges_pushes_active_wagers_without_today_checkin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = date(2026, 5, 27)
    sb = FakeSupabase()
    sb.table("wagers").rows.extend(
        [
            {
                "id": "w-needs-nudge",
                "user_id": "u1",
                "goal": "Lift 3x/wk",
                "stake_cents": 5000,
                "start_at": "2026-05-20",
                "end_at": "2026-06-20",
                "status": "active",
            },
            {
                "id": "w-already-checked",
                "user_id": "u1",
                "goal": "Cold showers daily",
                "stake_cents": 2500,
                "start_at": "2026-05-20",
                "end_at": "2026-06-20",
                "status": "active",
            },
            {
                "id": "w-not-active",
                "user_id": "u2",
                "goal": "Should be skipped",
                "stake_cents": 1000,
                "start_at": "2026-05-20",
                "end_at": "2026-06-20",
                "status": "succeeded",
            },
            {
                "id": "w-outside-window",
                "user_id": "u3",
                "goal": "Should be skipped",
                "stake_cents": 1000,
                "start_at": "2026-06-01",
                "end_at": "2026-06-20",
                "status": "active",
            },
        ]
    )
    sb.table("wager_checkins").rows.append(
        {
            "id": 1,
            "wager_id": "w-already-checked",
            "checkin_date": today.isoformat(),
            "status": "completed",
        }
    )

    push_calls: list[dict[str, Any]] = []

    async def fake_deliver(**kwargs: Any) -> list[Any]:
        push_calls.append(kwargs)
        # Pretend we sent successfully so the counter increments.
        return [type("R", (), {"status": "sent"})()]

    monkeypatch.setattr(nudges_mod, "deliver_to_user", fake_deliver)

    result = await run_nudges(today=today, supabase=sb)

    # `eligible` counts wagers that survive the active + window filter —
    # both w-needs-nudge and w-already-checked qualify. The latter is
    # then counted as skipped because today's checkin already exists.
    # w-not-active and w-outside-window never reach the inner loop.
    assert result.eligible == 2
    assert result.sent == 1
    assert result.skipped == 1
    assert len(push_calls) == 1
    call = push_calls[0]
    assert call["template"] == "wager_checkin"
    assert call["user_id"] == "u1"
    assert call["variables"] == {"wager_goal": "Lift 3x/wk", "stake": "50"}
    assert call["idempotency_key"] == "push:wager_checkin:w-needs-nudge:2026-05-27"
    assert "/wagers/w-needs-nudge" in call["deep_link"]


async def test_run_nudges_skips_when_push_returns_no_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A muted user (or zero subs) makes deliver_to_user return []. The
    nudge counter should report this as skipped, not sent — otherwise
    metrics over-report actual reach.
    """

    today = date(2026, 5, 27)
    sb = FakeSupabase()
    sb.table("wagers").rows.append(
        {
            "id": "w1",
            "user_id": "u1",
            "goal": "x",
            "stake_cents": 1000,
            "start_at": "2026-05-20",
            "end_at": "2026-06-20",
            "status": "active",
        }
    )

    async def fake_deliver(**_kwargs: Any) -> list[Any]:
        return []

    monkeypatch.setattr(nudges_mod, "deliver_to_user", fake_deliver)

    result = await run_nudges(today=today, supabase=sb)
    assert result.eligible == 1
    assert result.sent == 0
    assert result.skipped == 1


async def test_run_nudges_swallows_push_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A blowup in deliver_to_user must not crash the batch."""

    today = date(2026, 5, 27)
    sb = FakeSupabase()
    sb.table("wagers").rows.extend(
        [
            {
                "id": "w1",
                "user_id": "u1",
                "goal": "x",
                "stake_cents": 1000,
                "start_at": "2026-05-20",
                "end_at": "2026-06-20",
                "status": "active",
            },
            {
                "id": "w2",
                "user_id": "u2",
                "goal": "y",
                "stake_cents": 1000,
                "start_at": "2026-05-20",
                "end_at": "2026-06-20",
                "status": "active",
            },
        ]
    )

    calls = 0

    async def flaky(**_kwargs: Any) -> list[Any]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("push pipeline blew up")
        return [type("R", (), {"status": "sent"})()]

    monkeypatch.setattr(nudges_mod, "deliver_to_user", flaky)

    result = await run_nudges(today=today, supabase=sb)
    assert result.eligible == 2
    assert result.sent == 1
    assert result.skipped == 1
