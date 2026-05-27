"""Onboarding-finish welcome email endpoint."""

from __future__ import annotations

import os
from typing import Any

import pytest

os.environ.setdefault("NEXT_PUBLIC_APP_URL", "https://quarrel.test")
os.environ.setdefault("LITELLM_PROXY_URL", "https://litellm.test")
os.environ.setdefault("LITELLM_MASTER_KEY", "test")
os.environ.setdefault("NEXT_PUBLIC_SUPABASE_URL", "https://supabase.test")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test")
os.environ.setdefault("NEXT_PUBLIC_SUPABASE_ANON_KEY", "test")
os.environ.setdefault("WORKERS_INTERNAL_SECRET", "test-secret")

from app.routes import onboarding as onboarding_mod
from app.routes.onboarding import send_welcome_email


# ----- Fake auth.admin -----------------------------------------------------


class FakeAuthAdmin:
    def __init__(self) -> None:
        self._users: dict[str, dict[str, str]] = {}

    async def get_user_by_id(self, user_id: str) -> Any:
        u = self._users.get(user_id)
        if u is None:
            return type("Res", (), {"user": None})()
        return type("Res", (), {"user": type("U", (), {"email": u["email"]})()})()


class FakeAuth:
    def __init__(self) -> None:
        self.admin = FakeAuthAdmin()


# ----- Fake supabase (table queries) --------------------------------------


class _Res:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, table: "_Table") -> None:
        self._table = table
        self._filters: list[tuple[str, Any]] = []
        self._single = False

    def select(self, _cols: str = "*") -> "_Query":
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, val))
        return self

    def single(self) -> "_Query":
        self._single = True
        return self

    async def execute(self) -> _Res:
        rows = [r for r in self._table.rows if all(r.get(c) == v for c, v in self._filters)]
        if self._single:
            return _Res(rows[0] if rows else None)
        return _Res(rows)


class _Table:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, _cols: str = "*") -> _Query:
        return _Query(self)


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, _Table] = {}
        self.auth = FakeAuth()

    def table(self, name: str) -> _Table:
        if name not in self.tables:
            self.tables[name] = _Table()
        return self.tables[name]


# ----- Tests --------------------------------------------------------------


async def test_send_welcome_email_uses_display_name(monkeypatch: pytest.MonkeyPatch) -> None:
    sb = FakeSupabase()
    user_id = "00000000-0000-0000-0000-000000000001"
    sb.table("profiles").rows.append(
        {"id": user_id, "display_name": "Rabbi", "username": "rabbi"}
    )
    sb.auth.admin._users[user_id] = {"email": "rabbi@example.test"}

    sent: list[dict[str, Any]] = []

    async def fake_send_email(**kwargs: Any) -> Any:
        sent.append(kwargs)
        return type("R", (), {"status": "sent"})()

    async def fake_get_supabase() -> FakeSupabase:
        return sb

    monkeypatch.setattr(onboarding_mod, "send_email", fake_send_email)
    monkeypatch.setattr(onboarding_mod, "get_supabase", fake_get_supabase)

    out = await send_welcome_email(user_id=user_id)
    assert out.ok is True and out.sent is True
    assert len(sent) == 1
    call = sent[0]
    assert call["template"] == "welcome"
    assert call["to_email"] == "rabbi@example.test"
    assert call["variables"] == {"display_name": "Rabbi"}
    assert call["idempotency_key"] == f"email:welcome:{user_id}"
    assert call["user_id"] == user_id


async def test_send_welcome_email_falls_back_to_username(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """display_name can be NULL on a freshly created profile that only
    has a username. The email shouldn't blank out 'Welcome, .' — use
    the username as the next-best greeting.
    """

    sb = FakeSupabase()
    user_id = "00000000-0000-0000-0000-000000000002"
    sb.table("profiles").rows.append(
        {"id": user_id, "display_name": None, "username": "rabbi"}
    )
    sb.auth.admin._users[user_id] = {"email": "x@example.test"}

    sent: list[dict[str, Any]] = []

    async def fake_send_email(**kwargs: Any) -> Any:
        sent.append(kwargs)
        return type("R", (), {"status": "sent"})()

    async def fake_get_supabase() -> FakeSupabase:
        return sb

    monkeypatch.setattr(onboarding_mod, "send_email", fake_send_email)
    monkeypatch.setattr(onboarding_mod, "get_supabase", fake_get_supabase)

    out = await send_welcome_email(user_id=user_id)
    assert out.ok is True
    assert sent[0]["variables"] == {"display_name": "rabbi"}


async def test_send_welcome_email_missing_email_returns_not_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User has no email on auth.users (rare; social-login edge). We
    can't send anything but the endpoint should return cleanly, not
    crash the onboarding finish flow.
    """

    sb = FakeSupabase()
    user_id = "00000000-0000-0000-0000-000000000003"
    sb.table("profiles").rows.append(
        {"id": user_id, "display_name": "Rabbi", "username": "rabbi"}
    )
    # NB: no auth.admin user seeded → get_user_by_id returns None.

    sent: list[dict[str, Any]] = []

    async def fake_send_email(**kwargs: Any) -> Any:
        sent.append(kwargs)
        return type("R", (), {"status": "sent"})()

    async def fake_get_supabase() -> FakeSupabase:
        return sb

    monkeypatch.setattr(onboarding_mod, "send_email", fake_send_email)
    monkeypatch.setattr(onboarding_mod, "get_supabase", fake_get_supabase)

    out = await send_welcome_email(user_id=user_id)
    assert out.ok is False and out.sent is False
    assert sent == []
