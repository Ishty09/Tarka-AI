"""Beta-invite sender tests (§27 step 72)."""

from __future__ import annotations

from typing import Any

import pytest

from app.config import Settings
from app.services import beta_invites as svc
from app.services.beta_invites import send_pending_invites


@pytest.fixture(autouse=True)
def _stub_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = Settings(
        NEXT_PUBLIC_APP_URL="https://quarrel.test",
        LITELLM_PROXY_URL="https://litellm.test",
        LITELLM_MASTER_KEY="x",
        NEXT_PUBLIC_SUPABASE_URL="https://supabase.test",
        SUPABASE_SERVICE_ROLE_KEY="x",
        NEXT_PUBLIC_SUPABASE_ANON_KEY="x",
    )
    monkeypatch.setattr(svc, "get_settings", lambda: fake)


# ----- Fake Supabase -------------------------------------------------------


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
        self._order_col: str | None = None
        self._order_desc = False

    def select(self, _cols: str = "*") -> "_Query":
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, "eq", val))
        return self

    def is_(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, "is", val))
        return self

    def order(self, col: str, desc: bool = False) -> "_Query":
        self._order_col = col
        self._order_desc = desc
        return self

    def limit(self, n: int) -> "_Query":
        self._limit = n
        return self

    def _matches(self, row: dict[str, Any]) -> bool:
        for col, op, val in self._filters:
            actual = row.get(col)
            if op == "eq" and actual != val:
                return False
            if op == "is" and val == "null" and actual is not None:
                return False
        return True

    async def execute(self) -> _Res:
        if self._op == "select":
            filtered = [r for r in self._table.rows if self._matches(r)]
            if self._order_col is not None:
                filtered.sort(
                    key=lambda r: str(r.get(self._order_col) or ""),
                    reverse=self._order_desc,
                )
            if self._limit is not None:
                filtered = filtered[: self._limit]
            return _Res(filtered)
        if self._op == "update":
            updated = []
            for r in self._table.rows:
                if self._matches(r):
                    r.update(self._payload)
                    updated.append(r)
            return _Res(updated)
        return _Res([])


class _Table:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, _cols: str = "*") -> _Query:
        return _Query(self, "select")

    def update(self, payload: dict[str, Any]) -> _Query:
        return _Query(self, "update", payload)


class _FakeAdmin:
    def __init__(self) -> None:
        self.generate_calls: list[dict[str, Any]] = []
        self.next_link: str | None = "https://quarrel.test/onboarding?token=abc"
        self.should_raise = False

    async def generate_link(self, payload: dict[str, Any]) -> Any:
        self.generate_calls.append(payload)
        if self.should_raise:
            raise RuntimeError("supabase down")

        class _Props:
            def __init__(self, link: str | None) -> None:
                self.action_link = link

        class _Resp:
            def __init__(self, link: str | None) -> None:
                self.properties = _Props(link)

        return _Resp(self.next_link)


class _FakeAuth:
    def __init__(self) -> None:
        self.admin = _FakeAdmin()


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, _Table] = {}
        self.auth = _FakeAuth()

    def table(self, name: str) -> _Table:
        if name not in self.tables:
            self.tables[name] = _Table(name)
        return self.tables[name]


def _seed_invite(sb: FakeSupabase, *, invite_id: str, email: str) -> None:
    sb.table("beta_invites").rows.append(
        {
            "id": invite_id,
            "email": email,
            "cohort_tag": "wave-1",
            "notes": None,
            "sent_at": None,
            "error_message": None,
            "created_at": "2026-05-24T00:00:00+00:00",
        }
    )


# ----- Tests ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_pending_drains_and_stamps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sb = FakeSupabase()
    _seed_invite(sb, invite_id="inv-1", email="alice@example.com")

    sent: list[dict[str, Any]] = []

    async def fake_send(**kwargs: Any) -> Any:
        sent.append(kwargs)

    monkeypatch.setattr(svc, "send_email", fake_send)

    result = await send_pending_invites(supabase=sb)  # type: ignore[arg-type]

    assert result == {"sent": 1, "failed": 0, "queued": 1}
    assert sent[0]["template"] == "beta_invite"
    assert sent[0]["to_email"] == "alice@example.com"
    assert sent[0]["variables"]["signup_url"].startswith("https://")
    assert sb.auth.admin.generate_calls[0]["email"] == "alice@example.com"
    # Row is stamped.
    row = sb.table("beta_invites").rows[0]
    assert row["sent_at"] is not None
    assert row["expires_at"] is not None


@pytest.mark.asyncio
async def test_send_pending_skips_already_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sb = FakeSupabase()
    _seed_invite(sb, invite_id="inv-1", email="alice@example.com")
    sb.table("beta_invites").rows[0]["sent_at"] = "2026-05-24T00:00:00+00:00"

    sent: list[Any] = []

    async def fake_send(**kwargs: Any) -> Any:
        sent.append(kwargs)

    monkeypatch.setattr(svc, "send_email", fake_send)

    result = await send_pending_invites(supabase=sb)  # type: ignore[arg-type]

    assert result == {"sent": 0, "failed": 0, "queued": 0}
    assert sent == []


@pytest.mark.asyncio
async def test_send_pending_marks_invalid_email_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sb = FakeSupabase()
    _seed_invite(sb, invite_id="inv-1", email="not-an-email")

    async def fake_send(**_kw: Any) -> Any:
        return None

    monkeypatch.setattr(svc, "send_email", fake_send)

    result = await send_pending_invites(supabase=sb)  # type: ignore[arg-type]

    assert result == {"sent": 0, "failed": 1, "queued": 1}
    row = sb.table("beta_invites").rows[0]
    assert row["sent_at"] is None
    assert row["error_message"] == "invalid email"


@pytest.mark.asyncio
async def test_send_pending_handles_supabase_admin_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sb = FakeSupabase()
    _seed_invite(sb, invite_id="inv-1", email="alice@example.com")
    sb.auth.admin.should_raise = True

    async def fake_send(**_kw: Any) -> Any:
        raise AssertionError("send_email shouldn't be called when link gen fails")

    monkeypatch.setattr(svc, "send_email", fake_send)

    result = await send_pending_invites(supabase=sb)  # type: ignore[arg-type]

    assert result == {"sent": 0, "failed": 1, "queued": 1}
    row = sb.table("beta_invites").rows[0]
    assert row["error_message"] == "failed to generate magic link"


@pytest.mark.asyncio
async def test_send_pending_handles_send_email_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sb = FakeSupabase()
    _seed_invite(sb, invite_id="inv-1", email="alice@example.com")

    async def fake_send(**_kw: Any) -> Any:
        raise RuntimeError("resend down")

    monkeypatch.setattr(svc, "send_email", fake_send)

    result = await send_pending_invites(supabase=sb)  # type: ignore[arg-type]

    assert result == {"sent": 0, "failed": 1, "queued": 1}
    row = sb.table("beta_invites").rows[0]
    assert row["sent_at"] is None
    assert row["error_message"] is not None
    assert "resend" in row["error_message"]
