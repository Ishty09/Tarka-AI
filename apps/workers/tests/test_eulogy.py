"""Eulogy service tests.

Stubs the LLM and Supabase. Covers the helpers (quarter math), each LLM
defensive-deny path, persistence idempotency, tier gating, and the full
run_for_user happy path.
"""

from __future__ import annotations

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

from app.services import eulogy as eulogy_mod
from app.services.eulogy import (
    MIN_CONTENT_CHARS,
    _notify_eulogy_ready,
    generate_eulogy_text,
    persist_eulogy,
    previous_quarter_window,
    quarter_slug,
    run_for_user,
    run_quarter,
)
from app.services.llm import LiteLLMError, LiteLLMNetworkError


# ----- Quarter helpers ------------------------------------------------------


def test_quarter_slug_buckets_months_correctly() -> None:
    assert quarter_slug(datetime(2026, 1, 15, tzinfo=UTC)) == "2026-Q1"
    assert quarter_slug(datetime(2026, 3, 31, tzinfo=UTC)) == "2026-Q1"
    assert quarter_slug(datetime(2026, 4, 1, tzinfo=UTC)) == "2026-Q2"
    assert quarter_slug(datetime(2026, 12, 31, tzinfo=UTC)) == "2026-Q4"


def test_previous_quarter_window_at_quarter_boundary() -> None:
    # Job fires on April 1 → previous quarter is 2026-Q1.
    slug, start, end = previous_quarter_window(datetime(2026, 4, 1, 0, 0, tzinfo=UTC))
    assert slug == "2026-Q1"
    assert start == datetime(2026, 1, 1, tzinfo=UTC)
    assert end == datetime(2026, 4, 1, tzinfo=UTC)


def test_previous_quarter_window_january_wraps_year() -> None:
    slug, start, end = previous_quarter_window(datetime(2026, 1, 1, tzinfo=UTC))
    assert slug == "2025-Q4"
    assert start == datetime(2025, 10, 1, tzinfo=UTC)
    assert end == datetime(2026, 1, 1, tzinfo=UTC)


# ----- LLM stub --------------------------------------------------------------


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


GOOD_EULOGY = "You said you'd quit, then you didn't. " * 20  # ~ 600 chars


def _signals_with_facts() -> dict[str, list[Any]]:
    return {
        "facts": [{"fact": "User said X.", "category": "belief"}],
        "wagers": [],
        "checkins": [],
        "streaks": [],
    }


# ----- generate_eulogy_text -------------------------------------------------


async def test_generate_returns_text_on_happy_path() -> None:
    llm = FakeLLM(content=GOOD_EULOGY)
    content = await generate_eulogy_text(
        signals=_signals_with_facts(),
        client=llm,  # type: ignore[arg-type]
    )
    assert content is not None
    assert "you" in content.lower()


async def test_generate_returns_none_when_all_signals_empty() -> None:
    llm = FakeLLM(content="should not be called")
    content = await generate_eulogy_text(
        signals={"facts": [], "wagers": [], "checkins": [], "streaks": []},
        client=llm,  # type: ignore[arg-type]
    )
    assert content is None
    assert llm.calls == []


async def test_generate_returns_none_on_llm_error() -> None:
    llm = FakeLLM(exc=LiteLLMNetworkError("down"))
    content = await generate_eulogy_text(
        signals=_signals_with_facts(),
        client=llm,  # type: ignore[arg-type]
    )
    assert content is None


async def test_generate_returns_none_on_http_error() -> None:
    llm = FakeLLM(exc=LiteLLMError("500", 500, "x"))
    content = await generate_eulogy_text(
        signals=_signals_with_facts(),
        client=llm,  # type: ignore[arg-type]
    )
    assert content is None


async def test_generate_rejects_too_short_output() -> None:
    short = "Brief."
    assert len(short) < MIN_CONTENT_CHARS
    llm = FakeLLM(content=short)
    content = await generate_eulogy_text(
        signals=_signals_with_facts(),
        client=llm,  # type: ignore[arg-type]
    )
    assert content is None


# ----- Fake Supabase --------------------------------------------------------


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


def _seed_user(
    sb: FakeSupabase,
    user_id: str,
    *,
    tier: str,
    period_start: datetime,
    facts: list[str],
) -> None:
    sb.table("profiles").rows.append({"id": user_id, "tier": tier})
    inside_iso = (period_start + timedelta(days=10)).isoformat()
    for fact in facts:
        sb.table("user_facts").rows.append(
            {
                "user_id": user_id,
                "fact": fact,
                "category": "belief",
                "is_active": True,
                "created_at": inside_iso,
            }
        )


# ----- persist_eulogy + run_for_user ----------------------------------------


async def test_persist_idempotent_on_same_quarter() -> None:
    sb = FakeSupabase()
    first = await persist_eulogy(
        sb,  # type: ignore[arg-type]
        user_id="u",
        quarter="2026-Q1",
        content=GOOD_EULOGY,
    )
    second = await persist_eulogy(
        sb,  # type: ignore[arg-type]
        user_id="u",
        quarter="2026-Q1",
        content=GOOD_EULOGY + " amended",
    )
    assert first is True
    assert second is False
    rows = sb.table("eulogy_reports").rows
    assert len(rows) == 1
    # Original content kept because the second call ignored.
    assert rows[0]["content"] == GOOD_EULOGY


async def test_run_for_user_no_signal_short_circuits() -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.append({"id": "u", "tier": "pro"})
    llm = FakeLLM(content=GOOD_EULOGY)
    result = await run_for_user(
        sb,  # type: ignore[arg-type]
        user_id="u",
        quarter="2026-Q1",
        period_start=datetime(2026, 1, 1, tzinfo=UTC),
        period_end=datetime(2026, 4, 1, tzinfo=UTC),
        client=llm,  # type: ignore[arg-type]
    )
    assert result.inserted is False
    assert result.reason == "no_signal"
    assert llm.calls == []


async def test_run_for_user_inserts_on_happy_path() -> None:
    sb = FakeSupabase()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    _seed_user(sb, "u", tier="pro", period_start=start, facts=["User said X."])
    llm = FakeLLM(content=GOOD_EULOGY)
    result = await run_for_user(
        sb,  # type: ignore[arg-type]
        user_id="u",
        quarter="2026-Q1",
        period_start=start,
        period_end=datetime(2026, 4, 1, tzinfo=UTC),
        client=llm,  # type: ignore[arg-type]
    )
    assert result.inserted is True
    rows = sb.table("eulogy_reports").rows
    assert len(rows) == 1
    assert rows[0]["quarter"] == "2026-Q1"


# ----- run_quarter tier gating ---------------------------------------------


async def test_notify_eulogy_ready_fires_push_and_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Push (eulogy_ready, with the quarter slug substituted into the
    title) AND email (eulogy_ready) when a fresh eulogy lands.
    """

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

    monkeypatch.setattr(eulogy_mod, "deliver_to_user", fake_push)
    monkeypatch.setattr(eulogy_mod, "send_email", fake_email)
    monkeypatch.setattr(eulogy_mod, "_resolve_email", fake_resolve_email)

    await _notify_eulogy_ready(object(), user_id="u-eulogy", quarter="2026-Q1")  # type: ignore[arg-type]

    assert len(push_calls) == 1
    pcall = push_calls[0]
    assert pcall["template"] == "eulogy_ready"
    assert pcall["variables"] == {"quarter": "2026-Q1"}
    assert pcall["idempotency_key"] == "push:eulogy_ready:u-eulogy:2026-Q1"

    assert len(email_calls) == 1
    ecall = email_calls[0]
    assert ecall["template"] == "eulogy_ready"
    assert ecall["variables"] == {"quarter": "2026-Q1"}
    assert ecall["idempotency_key"] == "email:eulogy_ready:u-eulogy:2026-Q1"


async def test_run_quarter_skips_free_tier() -> None:
    sb = FakeSupabase()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 4, 1, tzinfo=UTC)
    _seed_user(sb, "free-user", tier="free", period_start=start, facts=["a"])
    _seed_user(sb, "max-user", tier="max", period_start=start, facts=["b"])
    llm = FakeLLM(content=GOOD_EULOGY)
    result = await run_quarter(
        quarter="2026-Q1",
        period_start=start,
        period_end=end,
        client=llm,  # type: ignore[arg-type]
        supabase=sb,  # type: ignore[arg-type]
    )
    assert result == {"eligible_users": 1, "inserted": 1, "skipped": 0}
    rows = sb.table("eulogy_reports").rows
    assert len(rows) == 1
    assert rows[0]["user_id"] == "max-user"
