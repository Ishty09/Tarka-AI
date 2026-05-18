"""Daily Roast scheduling + generation tests.

Covers: timezone-aware eligibility window, persona resolution, top-facts
retrieval, generation defensive paths, dedupe via prior roast message,
auto-creation of the per-user "Daily Roast" conversation, end-to-end
deliver_one + run_window.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any

import pytest

from app.services.daily_roast import (
    MAX_ROAST_CHARS,
    MIN_ROAST_CHARS,
    RoastRecipient,
    deliver_one,
    fetch_top_facts,
    find_eligible_users,
    generate_roast,
    get_or_create_daily_roast_conversation,
    has_recent_roast,
    run_window,
)
from app.services.llm import LiteLLMError, LiteLLMNetworkError


PERSONA_SLUG = "british_boomer_dad"


# ----- Stubs ---------------------------------------------------------------


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
        self._order: list[tuple[str, bool]] = []

    def select(self, _cols: str = "*") -> "_Query":
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, "eq", val))
        return self

    def gte(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, "gte", val))
        return self

    def in_(self, col: str, vals: list[Any]) -> "_Query":
        self._filters.append((col, "in", vals))
        return self

    @property
    def not_(self) -> "_NotProxy":
        return _NotProxy(self)

    def order(self, col: str, desc: bool = False) -> "_Query":
        self._order.append((col, desc))
        return self

    def limit(self, n: int) -> "_Query":
        self._limit = n
        return self

    async def execute(self) -> _Res:
        if self._op == "select":
            rows = list(self._table.rows)
            for col, op, val in self._filters:
                if op == "eq":
                    rows = [r for r in rows if r.get(col) == val]
                elif op == "gte":
                    rows = [r for r in rows if str(r.get(col, "")) >= str(val)]
                elif op == "in":
                    rows = [r for r in rows if r.get(col) in val]
                elif op == "not_null":
                    rows = [r for r in rows if r.get(col) is not None]
            for col, desc in reversed(self._order):
                rows.sort(key=lambda r: r.get(col) or "", reverse=desc)
            if self._limit is not None:
                rows = rows[: self._limit]
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

    def seed_persona(self) -> str:
        self.table("personas").rows.append(
            {"id": "persona-id", "slug": PERSONA_SLUG, "name": "British Boomer Dad"}
        )
        return "persona-id"


def _recipient(**overrides: Any) -> RoastRecipient:
    base = {
        "user_id": "u",
        "username": "rabbi",
        "persona_slug": PERSONA_SLUG,
        "persona_id": "persona-id",
        "persona_name": "British Boomer Dad",
        "locale": "en",
        "timezone": "UTC",
    }
    base.update(overrides)
    return RoastRecipient(**base)


# ----- find_eligible_users -------------------------------------------------


async def test_find_eligible_users_picks_user_in_window() -> None:
    sb = FakeSupabase()
    sb.seed_persona()
    sb.table("profiles").rows.append(
        {
            "id": "u",
            "username": "rabbi",
            "timezone": "UTC",
            "locale": "en",
            "daily_roast_time": "09:00:00",
            "daily_roast_persona_slug": PERSONA_SLUG,
            "notification_push": True,
            "is_suspended": False,
        }
    )

    now = datetime(2026, 5, 18, 9, 5, 0, tzinfo=UTC)  # 9:05 UTC — inside (8:50, 9:05]
    recipients = await find_eligible_users(sb, now_utc=now)  # type: ignore[arg-type]
    assert len(recipients) == 1
    assert recipients[0].user_id == "u"
    assert recipients[0].persona_id == "persona-id"


async def test_find_eligible_users_skips_outside_window() -> None:
    sb = FakeSupabase()
    sb.seed_persona()
    sb.table("profiles").rows.append(
        {
            "id": "u",
            "username": "rabbi",
            "timezone": "UTC",
            "daily_roast_time": "09:00:00",
            "daily_roast_persona_slug": PERSONA_SLUG,
            "notification_push": True,
            "is_suspended": False,
        }
    )
    # 10:30 UTC — way past 9:00.
    now = datetime(2026, 5, 18, 10, 30, 0, tzinfo=UTC)
    recipients = await find_eligible_users(sb, now_utc=now)  # type: ignore[arg-type]
    assert recipients == []


async def test_find_eligible_users_respects_timezone() -> None:
    sb = FakeSupabase()
    sb.seed_persona()
    sb.table("profiles").rows.append(
        {
            "id": "u",
            "username": "rabbi",
            "timezone": "Asia/Dhaka",  # UTC+6 (no DST)
            "daily_roast_time": "09:00:00",
            "daily_roast_persona_slug": PERSONA_SLUG,
            "notification_push": True,
            "is_suspended": False,
        }
    )
    # 03:05 UTC = 09:05 Dhaka → inside window
    now = datetime(2026, 5, 18, 3, 5, 0, tzinfo=UTC)
    assert (await find_eligible_users(sb, now_utc=now)) != []  # type: ignore[arg-type]

    # 06:00 UTC = 12:00 Dhaka → outside
    now2 = datetime(2026, 5, 18, 6, 0, 0, tzinfo=UTC)
    assert (await find_eligible_users(sb, now_utc=now2)) == []  # type: ignore[arg-type]


async def test_find_eligible_users_skips_suspended_or_push_off() -> None:
    sb = FakeSupabase()
    sb.seed_persona()
    sb.table("profiles").rows.extend([
        {
            "id": "suspended",
            "username": "x",
            "timezone": "UTC",
            "daily_roast_time": "09:00:00",
            "daily_roast_persona_slug": PERSONA_SLUG,
            "notification_push": True,
            "is_suspended": True,
        },
        {
            "id": "push_off",
            "username": "y",
            "timezone": "UTC",
            "daily_roast_time": "09:00:00",
            "daily_roast_persona_slug": PERSONA_SLUG,
            "notification_push": False,
            "is_suspended": False,
        },
    ])
    now = datetime(2026, 5, 18, 9, 5, 0, tzinfo=UTC)
    recipients = await find_eligible_users(sb, now_utc=now)  # type: ignore[arg-type]
    assert recipients == []


async def test_find_eligible_users_skips_when_persona_missing_from_lookup() -> None:
    sb = FakeSupabase()
    # No personas table seeded.
    sb.table("profiles").rows.append(
        {
            "id": "u",
            "username": "rabbi",
            "timezone": "UTC",
            "daily_roast_time": "09:00:00",
            "daily_roast_persona_slug": "ghost_persona",
            "notification_push": True,
            "is_suspended": False,
        }
    )
    now = datetime(2026, 5, 18, 9, 5, 0, tzinfo=UTC)
    recipients = await find_eligible_users(sb, now_utc=now)  # type: ignore[arg-type]
    assert recipients == []


# ----- fetch_top_facts -----------------------------------------------------


async def test_fetch_top_facts_orders_by_confidence_then_recency() -> None:
    sb = FakeSupabase()
    sb.table("user_facts").rows.extend([
        {"fact": "old high conf", "confidence": 0.95, "category": "belief",
         "is_active": True, "user_id": "u", "created_at": "2026-01-01"},
        {"fact": "new low conf", "confidence": 0.5, "category": "belief",
         "is_active": True, "user_id": "u", "created_at": "2026-05-01"},
        {"fact": "new high conf", "confidence": 0.95, "category": "belief",
         "is_active": True, "user_id": "u", "created_at": "2026-05-10"},
    ])
    facts = await fetch_top_facts(sb, user_id="u", limit=2)  # type: ignore[arg-type]
    # Highest confidence first; tie broken by recency.
    assert facts[0] == "new high conf"
    assert facts[1] == "old high conf"


# ----- generate_roast ------------------------------------------------------


async def test_generate_roast_strips_quotes_and_returns_text() -> None:
    text = "Your `goal` of writing daily is still a noun. Verbs would help."
    llm = FakeLLM(content=f'"{text}"')
    out = await generate_roast(_recipient(), ["fact 1"], client=llm)  # type: ignore[arg-type]
    assert out is not None
    assert out == text


async def test_generate_roast_too_short_returns_none() -> None:
    llm = FakeLLM(content="Short.")
    out = await generate_roast(_recipient(), [], client=llm)  # type: ignore[arg-type]
    assert out is None


async def test_generate_roast_truncates_over_max() -> None:
    over = "x" * (MAX_ROAST_CHARS + 100)
    llm = FakeLLM(content=over)
    out = await generate_roast(_recipient(), ["f"], client=llm)  # type: ignore[arg-type]
    assert out is not None
    assert len(out) <= MAX_ROAST_CHARS


async def test_generate_roast_llm_error_returns_none() -> None:
    llm = FakeLLM(exc=LiteLLMNetworkError("down"))
    assert (
        await generate_roast(_recipient(), ["f"], client=llm)  # type: ignore[arg-type]
    ) is None


async def test_generate_roast_http_error_returns_none() -> None:
    llm = FakeLLM(exc=LiteLLMError("500", 500, "x"))
    assert (
        await generate_roast(_recipient(), ["f"], client=llm)  # type: ignore[arg-type]
    ) is None


# ----- has_recent_roast ----------------------------------------------------


async def test_has_recent_roast_finds_marker() -> None:
    sb = FakeSupabase()
    now = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)
    sb.table("messages").rows.append(
        {
            "user_id": "u",
            "role": "assistant",
            "created_at": (now - timedelta(hours=4)).isoformat(),
            "metadata": {"kind": "daily_roast"},
        }
    )
    assert (
        await has_recent_roast(sb, user_id="u", now_utc=now)  # type: ignore[arg-type]
    ) is True


async def test_has_recent_roast_ignores_other_kinds() -> None:
    sb = FakeSupabase()
    now = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)
    sb.table("messages").rows.append(
        {
            "user_id": "u",
            "role": "assistant",
            "created_at": (now - timedelta(hours=4)).isoformat(),
            "metadata": {"kind": "council_verdict"},
        }
    )
    assert (
        await has_recent_roast(sb, user_id="u", now_utc=now)  # type: ignore[arg-type]
    ) is False


# ----- get_or_create_daily_roast_conversation ------------------------------


async def test_creates_new_conversation_on_first_run() -> None:
    sb = FakeSupabase()
    cid = await get_or_create_daily_roast_conversation(
        sb,  # type: ignore[arg-type]
        recipient=_recipient(),
    )
    convo = sb.table("conversations").rows[0]
    assert convo["id"] == cid
    assert convo["mode"] == "roast"
    assert convo["metadata"]["kind"] == "daily_roast"
    assert convo["persona_id"] == "persona-id"


async def test_reuses_existing_conversation_on_second_run() -> None:
    sb = FakeSupabase()
    existing = "existing-convo"
    sb.table("conversations").rows.append(
        {
            "id": existing,
            "user_id": "u",
            "mode": "roast",
            "archived": False,
            "metadata": {"kind": "daily_roast", "persona_slug": PERSONA_SLUG},
        }
    )
    cid = await get_or_create_daily_roast_conversation(
        sb,  # type: ignore[arg-type]
        recipient=_recipient(),
    )
    assert cid == existing
    # No second row inserted.
    assert len(sb.table("conversations").rows) == 1


# ----- deliver_one ---------------------------------------------------------


GOOD_ROAST = "Your gym fact is louder than your gym. Goal posts moved again."


async def test_deliver_one_creates_message_and_conversation() -> None:
    sb = FakeSupabase()
    sb.seed_persona()
    sb.table("user_facts").rows.append(
        {
            "user_id": "u",
            "fact": "User said they'd go to the gym 4x/week.",
            "confidence": 0.9,
            "category": "commitment",
            "is_active": True,
            "created_at": "2026-05-10",
        }
    )
    now = datetime(2026, 5, 18, 9, 0, 0, tzinfo=UTC)
    llm = FakeLLM(content=GOOD_ROAST)

    run = await deliver_one(
        sb,  # type: ignore[arg-type]
        recipient=_recipient(),
        now_utc=now,
        client=llm,  # type: ignore[arg-type]
    )
    assert run is not None
    assert run.text == GOOD_ROAST
    # One conversation, one message — message has kind='daily_roast' metadata.
    msgs = sb.table("messages").rows
    assert len(msgs) == 1
    assert msgs[0]["metadata"]["kind"] == "daily_roast"
    assert msgs[0]["content"] == GOOD_ROAST


async def test_deliver_one_dedupe_skips() -> None:
    sb = FakeSupabase()
    sb.seed_persona()
    now = datetime(2026, 5, 18, 9, 0, 0, tzinfo=UTC)
    # Existing roast within window.
    sb.table("messages").rows.append(
        {
            "user_id": "u",
            "role": "assistant",
            "created_at": (now - timedelta(hours=4)).isoformat(),
            "metadata": {"kind": "daily_roast"},
        }
    )
    llm = FakeLLM(content=GOOD_ROAST)
    run = await deliver_one(
        sb,  # type: ignore[arg-type]
        recipient=_recipient(),
        now_utc=now,
        client=llm,  # type: ignore[arg-type]
    )
    assert run is None
    # No new roast persisted.
    assert all(
        not (isinstance(m.get("metadata"), dict) and m["metadata"].get("kind") == "daily_roast" and m.get("content") == GOOD_ROAST)
        for m in sb.table("messages").rows
    )


async def test_deliver_one_llm_failure_no_persistence() -> None:
    sb = FakeSupabase()
    sb.seed_persona()
    now = datetime(2026, 5, 18, 9, 0, 0, tzinfo=UTC)
    llm = FakeLLM(exc=LiteLLMNetworkError("down"))
    run = await deliver_one(
        sb,  # type: ignore[arg-type]
        recipient=_recipient(),
        now_utc=now,
        client=llm,  # type: ignore[arg-type]
    )
    assert run is None
    # No conversation created because we bailed before persistence.
    assert "conversations" not in sb.tables or sb.tables["conversations"].rows == []


# ----- run_window end-to-end -----------------------------------------------


async def test_run_window_delivers_one_user() -> None:
    sb = FakeSupabase()
    sb.seed_persona()
    sb.table("profiles").rows.append(
        {
            "id": "u",
            "username": "rabbi",
            "timezone": "UTC",
            "locale": "en",
            "daily_roast_time": "09:00:00",
            "daily_roast_persona_slug": PERSONA_SLUG,
            "notification_push": True,
            "is_suspended": False,
        }
    )
    now = datetime(2026, 5, 18, 9, 5, 0, tzinfo=UTC)
    llm = FakeLLM(content=GOOD_ROAST)
    result = await run_window(
        now_utc=now,
        client=llm,  # type: ignore[arg-type]
        supabase=sb,  # type: ignore[arg-type]
    )
    assert result == {"eligible": 1, "delivered": 1, "skipped": 0}
