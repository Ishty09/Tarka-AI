"""Drill Sergeant cron tests."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from app.services.drill_sergeant import (
    MIN_ROAST_CHARS,
    StreakCandidate,
    deliver,
    find_streaks_needing_nudge,
    generate_drill_message,
    persist_drill_message,
    run_today,
)
from app.services.llm import LiteLLMError, LiteLLMNetworkError


HOST_SLUG = "devils_advocate"
GOOD_ROAST = "Three days of pretending the habit was a phase. You named it; now name what you're doing instead."


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
        self._order_desc = False

    def select(self, _cols: str = "*") -> "_Query":
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, "eq", val))
        return self

    @property
    def not_(self) -> "_NotProxy":
        return _NotProxy(self)

    def order(self, _col: str, desc: bool = False) -> "_Query":
        self._order_desc = desc
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
                elif op == "not_null":
                    rows = [r for r in rows if r.get(col) is not None]
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


class _NotProxy:
    def __init__(self, parent: _Query) -> None:
        self._parent = parent

    def is_(self, col: str, val: Any) -> _Query:
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


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, _Table] = {}

    def table(self, name: str) -> _Table:
        if name not in self.tables:
            self.tables[name] = _Table(name)
        return self.tables[name]

    def seed_host(self) -> None:
        self.table("personas").rows.append({"id": "host-id", "slug": HOST_SLUG})

    def seed_streak(
        self,
        *,
        streak_id: int,
        user_id: str = "u",
        habit: str = "Write 500 words/day",
        last: str | None = None,
        longest: int = 0,
    ) -> None:
        self.table("streaks").rows.append(
            {
                "id": streak_id,
                "user_id": user_id,
                "habit": habit,
                "last_checkin_at": last,
                "longest_streak": longest,
            }
        )


def _candidate(*, tier: int, last: str = "2026-05-12", streak_id: int = 1) -> StreakCandidate:
    return StreakCandidate(
        streak_id=streak_id,
        user_id="u",
        habit="Write 500 words/day",
        last_checkin_at=date.fromisoformat(last),
        longest_streak=14,
        tier=tier,
    )


# ----- find_streaks_needing_nudge ------------------------------------------


async def test_find_picks_streaks_at_escalation_thresholds() -> None:
    sb = FakeSupabase()
    today = date(2026, 5, 19)
    # 1 day ago — tier 1
    sb.seed_streak(streak_id=1, last=(today - timedelta(days=1)).isoformat())
    # 3 days ago — tier 3
    sb.seed_streak(streak_id=2, last=(today - timedelta(days=3)).isoformat())
    # 5 days ago — NOT a threshold
    sb.seed_streak(streak_id=3, last=(today - timedelta(days=5)).isoformat())
    # 7 days ago — tier 7
    sb.seed_streak(streak_id=4, last=(today - timedelta(days=7)).isoformat())
    # 14 days ago — tier 14
    sb.seed_streak(streak_id=5, last=(today - timedelta(days=14)).isoformat())
    # 30 days ago — NOT a threshold (past eulogy)
    sb.seed_streak(streak_id=6, last=(today - timedelta(days=30)).isoformat())
    # No last_checkin — skipped
    sb.seed_streak(streak_id=7, last=None)

    out = await find_streaks_needing_nudge(sb, today=today)  # type: ignore[arg-type]
    tiers = {(c.streak_id, c.tier) for c in out}
    assert tiers == {(1, 1), (2, 3), (4, 7), (5, 14)}


# ----- generate_drill_message ----------------------------------------------


async def test_generate_returns_text_for_each_tier() -> None:
    for tier in (1, 3, 7, 14):
        llm = FakeLLM(content=GOOD_ROAST)
        out = await generate_drill_message(_candidate(tier=tier), client=llm)  # type: ignore[arg-type]
        assert out is not None


async def test_generate_too_short_returns_none() -> None:
    short = "Brief."
    assert len(short) < MIN_ROAST_CHARS
    llm = FakeLLM(content=short)
    assert (
        await generate_drill_message(_candidate(tier=3), client=llm)  # type: ignore[arg-type]
    ) is None


async def test_generate_llm_error_returns_none() -> None:
    llm = FakeLLM(exc=LiteLLMNetworkError("down"))
    assert (
        await generate_drill_message(_candidate(tier=7), client=llm)  # type: ignore[arg-type]
    ) is None


async def test_generate_unknown_tier_returns_none() -> None:
    """Defensive: an integer that isn't in ESCALATION_TIERS shouldn't have a
    prompt. find_streaks_needing_nudge gates against this but the function
    should be defensive on its own.
    """

    llm = FakeLLM(content=GOOD_ROAST)
    weird = StreakCandidate(
        streak_id=1,
        user_id="u",
        habit="x",
        last_checkin_at=date(2026, 5, 12),
        longest_streak=0,
        tier=99,
    )
    assert (await generate_drill_message(weird, client=llm)) is None  # type: ignore[arg-type]


# ----- persist_drill_message -----------------------------------------------


async def test_persist_writes_dedupe_metadata() -> None:
    sb = FakeSupabase()
    msg_id = await persist_drill_message(
        sb,  # type: ignore[arg-type]
        candidate=_candidate(tier=3),
        text=GOOD_ROAST,
        conversation_id="convo-1",
    )
    assert msg_id is not None
    row = sb.table("messages").rows[0]
    assert row["metadata"]["kind"] == "drill_sergeant"
    assert row["metadata"]["streak_id"] == 1
    assert row["metadata"]["tier"] == 3
    assert row["metadata"]["since_checkin_at"] == "2026-05-12"


# ----- deliver (dedupe + happy path) ---------------------------------------


async def test_deliver_dedupes_same_tier_for_same_break() -> None:
    sb = FakeSupabase()
    sb.seed_host()
    candidate = _candidate(tier=3, last="2026-05-15")

    llm = FakeLLM(content=GOOD_ROAST)
    first = await deliver(sb, candidate=candidate, client=llm)  # type: ignore[arg-type]
    assert first is not None

    # Second call same break — should dedupe.
    second = await deliver(sb, candidate=candidate, client=llm)  # type: ignore[arg-type]
    assert second is None
    # Only one drill_sergeant message persisted.
    drill_msgs = [
        m for m in sb.table("messages").rows
        if isinstance(m.get("metadata"), dict)
        and m["metadata"].get("kind") == "drill_sergeant"
    ]
    assert len(drill_msgs) == 1


async def test_deliver_creates_conversation_once() -> None:
    sb = FakeSupabase()
    sb.seed_host()
    llm = FakeLLM(content=GOOD_ROAST)

    a = await deliver(
        sb,  # type: ignore[arg-type]
        candidate=_candidate(tier=1, streak_id=1, last="2026-05-18"),
        client=llm,  # type: ignore[arg-type]
    )
    b = await deliver(
        sb,  # type: ignore[arg-type]
        candidate=_candidate(tier=3, streak_id=2, last="2026-05-16"),
        client=llm,  # type: ignore[arg-type]
    )
    assert a is not None and b is not None
    assert a.conversation_id == b.conversation_id
    # One conversation row.
    assert len(sb.table("conversations").rows) == 1


# ----- run_today ----------------------------------------------------------


async def test_run_today_delivers_to_eligible_streak() -> None:
    sb = FakeSupabase()
    sb.seed_host()
    today = date(2026, 5, 19)
    sb.seed_streak(streak_id=42, last=(today - timedelta(days=3)).isoformat())
    llm = FakeLLM(content=GOOD_ROAST)
    result = await run_today(
        today=today,
        client=llm,  # type: ignore[arg-type]
        supabase=sb,  # type: ignore[arg-type]
    )
    assert result == {"candidates": 1, "delivered": 1, "skipped": 0}
