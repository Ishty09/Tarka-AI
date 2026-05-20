"""Enforcement helpers: suspension + quota."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import HTTPException

os.environ.setdefault("NEXT_PUBLIC_APP_URL", "https://quarrel.test")
os.environ.setdefault("LITELLM_PROXY_URL", "https://litellm.test")
os.environ.setdefault("LITELLM_MASTER_KEY", "test")
os.environ.setdefault("NEXT_PUBLIC_SUPABASE_URL", "https://supabase.test")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test")
os.environ.setdefault("NEXT_PUBLIC_SUPABASE_ANON_KEY", "test")

from app.services import enforcement
from app.services.enforcement import (
    SuspendedUserError,
    assert_not_suspended,
    check_quota,
    enforce_quota,
    enforce_user,
    quota_detail,
)
from app.services.quotas import QuotaState

# ----- Fakes ---------------------------------------------------------------


class _Res:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Q:
    def __init__(self, table: _Table) -> None:
        self._t = table
        self._filters: list[tuple[str, Any]] = []
        self._maybe_single = False

    def select(self, _cols: str = "*") -> _Q:
        return self

    def eq(self, col: str, val: Any) -> _Q:
        self._filters.append((col, val))
        return self

    def maybe_single(self) -> _Q:
        self._maybe_single = True
        return self

    async def execute(self) -> _Res:
        rows = [r for r in self._t.rows if all(r.get(c) == v for c, v in self._filters)]
        if self._maybe_single:
            return _Res(rows[0] if rows else None)
        return _Res(rows)


class _Table:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, _cols: str = "*") -> _Q:
        return _Q(self)


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, _Table] = {}

    def table(self, name: str) -> _Table:
        self.tables.setdefault(name, _Table())
        return self.tables[name]


# ----- Tests: suspension ---------------------------------------------------


@pytest.mark.asyncio
async def test_suspended_user_raises() -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.append(
        {"id": "u1", "is_suspended": True, "suspension_reason": "Spam"}
    )
    with pytest.raises(SuspendedUserError) as exc:
        await assert_not_suspended(sb, user_id="u1")  # type: ignore[arg-type]
    assert exc.value.status_code == 403
    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert detail["error"] == "user_suspended"
    assert detail["reason"] == "Spam"


@pytest.mark.asyncio
async def test_active_user_allowed() -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.append(
        {"id": "u1", "is_suspended": False, "suspension_reason": None}
    )
    await assert_not_suspended(sb, user_id="u1")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_missing_profile_does_not_raise() -> None:
    sb = FakeSupabase()
    await assert_not_suspended(sb, user_id="u_unknown")  # type: ignore[arg-type]


# ----- Tests: quota helpers ------------------------------------------------


def test_quota_detail_shape() -> None:
    reset = datetime(2026, 5, 21, tzinfo=UTC)
    state = QuotaState(tier="free", used=15, limit=15, reset_at=reset)
    out = quota_detail(state, scope="messages")
    assert out["error"] == "quota_exceeded"
    assert out["scope"] == "messages"
    assert out["tier"] == "free"
    assert out["limit"] == 15
    assert out["used"] == 15
    assert out["reset_at"] == reset.isoformat()
    assert out["upgrade_url"] == "/pricing"


@pytest.mark.asyncio
async def test_check_quota_returns_state(monkeypatch: pytest.MonkeyPatch) -> None:
    sb = FakeSupabase()
    state = QuotaState(
        tier="pro",
        used=4,
        limit=200,
        reset_at=datetime.now(UTC) + timedelta(hours=1),
    )

    async def fake_messages(_supabase: Any, _user_id: str) -> QuotaState:
        return state

    monkeypatch.setattr(enforcement, "get_message_quota", fake_messages)
    enforcement.SCOPE_GETTERS["messages"] = fake_messages

    out = await check_quota(sb, user_id="u1", scope="messages")  # type: ignore[arg-type]
    assert out is state


@pytest.mark.asyncio
async def test_enforce_quota_raises_429(monkeypatch: pytest.MonkeyPatch) -> None:
    sb = FakeSupabase()
    state = QuotaState(
        tier="free",
        used=15,
        limit=15,
        reset_at=datetime.now(UTC) + timedelta(hours=1),
    )

    async def fake_messages(_supabase: Any, _user_id: str) -> QuotaState:
        return state

    enforcement.SCOPE_GETTERS["messages"] = fake_messages

    with pytest.raises(HTTPException) as exc:
        await enforce_quota(sb, user_id="u1", scope="messages")  # type: ignore[arg-type]
    assert exc.value.status_code == 429
    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert detail["scope"] == "messages"
    assert detail["upgrade_url"] == "/pricing"


@pytest.mark.asyncio
async def test_enforce_quota_passes_under_limit() -> None:
    sb = FakeSupabase()
    state = QuotaState(
        tier="pro",
        used=10,
        limit=200,
        reset_at=datetime.now(UTC) + timedelta(hours=1),
    )

    async def fake_messages(_supabase: Any, _user_id: str) -> QuotaState:
        return state

    enforcement.SCOPE_GETTERS["messages"] = fake_messages

    out = await enforce_quota(sb, user_id="u1", scope="messages")  # type: ignore[arg-type]
    assert out is state


@pytest.mark.asyncio
async def test_enforce_user_runs_suspension_before_quota() -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.append(
        {"id": "u1", "is_suspended": True, "suspension_reason": "n/a"}
    )

    async def fake_messages(_supabase: Any, _user_id: str) -> QuotaState:
        return QuotaState(
            tier="free",
            used=15,
            limit=15,
            reset_at=datetime.now(UTC) + timedelta(hours=1),
        )

    enforcement.SCOPE_GETTERS["messages"] = fake_messages

    with pytest.raises(SuspendedUserError):
        await enforce_user(sb, user_id="u1", scope="messages")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_enforce_user_returns_none_when_no_scope() -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.append(
        {"id": "u1", "is_suspended": False, "suspension_reason": None}
    )
    out = await enforce_user(sb, user_id="u1", scope=None)  # type: ignore[arg-type]
    assert out is None
