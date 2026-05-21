"""Account-deletion sweeper tests (§27 step 58).

Notification phase: only fires for users with data_deletion_requested_at
AND no deletion_grace_notified_at, stamps the column after sending.

Hard-delete phase: only deletes users whose grace period has elapsed,
writes the audit_log row before calling auth.admin.delete_user, and
keeps the row on failures.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.config import Settings
from app.services import account_deletion as svc
from app.services.account_deletion import (
    GRACE_PERIOD,
    run_once,
    send_pending_grace_notifications,
    sweep_due_deletions,
)


@pytest.fixture(autouse=True)
def _stub_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide complete env so the service's get_settings() can resolve app_url."""

    fake = Settings(
        NEXT_PUBLIC_APP_URL="https://quarrel.test",
        LITELLM_PROXY_URL="https://litellm.test",
        LITELLM_MASTER_KEY="x",
        NEXT_PUBLIC_SUPABASE_URL="https://supabase.test",
        SUPABASE_SERVICE_ROLE_KEY="x",
        NEXT_PUBLIC_SUPABASE_ANON_KEY="x",
    )
    monkeypatch.setattr(svc, "get_settings", lambda: fake)


# ----- Fake Supabase --------------------------------------------------------


class _Res:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, table: _Table, op: str, payload: Any = None) -> None:
        self._table = table
        self._op = op
        self._payload = payload
        self._filters: list[tuple[str, str, Any]] = []
        self._order_col: str | None = None
        self._order_desc = False
        self._limit: int | None = None

    def select(self, _cols: str = "*") -> _Query:
        return self

    def eq(self, col: str, val: Any) -> _Query:
        self._filters.append((col, "eq", val))
        return self

    def is_(self, col: str, val: Any) -> _Query:
        # Supabase-py uses .is_(col, "null") for IS NULL checks.
        self._filters.append((col, "is", val))
        return self

    @property
    def not_(self) -> _NotQuery:
        return _NotQuery(self)

    def lte(self, col: str, val: Any) -> _Query:
        self._filters.append((col, "lte", val))
        return self

    def in_(self, col: str, vals: Iterable[Any]) -> _Query:
        self._filters.append((col, "in", list(vals)))
        return self

    def order(self, col: str, desc: bool = False) -> _Query:
        self._order_col = col
        self._order_desc = desc
        return self

    def limit(self, n: int) -> _Query:
        self._limit = n
        return self

    def _matches(self, row: dict[str, Any]) -> bool:
        for col, op, val in self._filters:
            actual = row.get(col)
            if op == "eq" and actual != val:
                return False
            if op == "is" and val == "null" and actual is not None:
                return False
            if op == "is_not_null" and actual is None:
                return False
            if op == "lte" and not (
                actual is not None and str(actual) <= str(val)
            ):
                return False
            if op == "in" and actual not in val:
                return False
        return True

    async def execute(self) -> _Res:
        rows = list(self._table.rows)
        if self._op == "select":
            filtered = [r for r in rows if self._matches(r)]
            if self._order_col is not None:
                filtered.sort(
                    key=lambda r: str(r.get(self._order_col) or ""),
                    reverse=self._order_desc,
                )
            if self._limit is not None:
                filtered = filtered[: self._limit]
            return _Res(filtered)

        if self._op == "update":
            updates: list[dict[str, Any]] = []
            for r in self._table.rows:
                if self._matches(r):
                    r.update(self._payload)
                    updates.append(r)
            return _Res(updates)

        if self._op == "insert":
            payload = (
                self._payload if isinstance(self._payload, list) else [self._payload]
            )
            for row in payload:
                self._table.rows.append(dict(row))
            return _Res(payload)

        return _Res([])


class _NotQuery:
    """Mimics supabase-py's `.not_.is_(col, "null")` for IS NOT NULL."""

    def __init__(self, parent: _Query) -> None:
        self._parent = parent

    def is_(self, col: str, val: Any) -> _Query:
        # not_.is_(col, "null") → IS NOT NULL.
        if val == "null":
            self._parent._filters.append((col, "is_not_null", None))
        return self._parent


class _Table:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, _cols: str = "*") -> _Query:
        return _Query(self, "select")

    def update(self, payload: dict[str, Any]) -> _Query:
        return _Query(self, "update", payload)

    def insert(self, payload: Any) -> _Query:
        return _Query(self, "insert", payload)


class _FakeAdmin:
    def __init__(self, *, users: dict[str, dict[str, str]]) -> None:
        self._users = users
        self.deleted: list[str] = []
        self.delete_should_fail: set[str] = set()

    async def get_user_by_id(self, user_id: str) -> Any:
        class _User:
            def __init__(self, email: str) -> None:
                self.email = email

        class _Resp:
            def __init__(self, email: str) -> None:
                self.user = _User(email)

        record = self._users.get(user_id, {"email": ""})
        return _Resp(record.get("email", ""))

    async def delete_user(self, user_id: str) -> None:
        if user_id in self.delete_should_fail:
            raise RuntimeError("delete denied")
        self.deleted.append(user_id)
        # Simulate the on-delete-cascade chain: profiles row goes away.
        # Other tables aren't relevant for these tests.


class _FakeAuth:
    def __init__(self, *, users: dict[str, dict[str, str]]) -> None:
        self.admin = _FakeAdmin(users=users)


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, _Table] = {}
        self.auth = _FakeAuth(users={})

    def table(self, name: str) -> _Table:
        if name not in self.tables:
            self.tables[name] = _Table(name)
        return self.tables[name]


# ----- Helpers --------------------------------------------------------------


def _seed_user(
    sb: FakeSupabase,
    *,
    user_id: str,
    requested_days_ago: float | None,
    notified: bool,
    email: str = "u@example.com",
    username: str = "user",
) -> None:
    now = datetime.now(UTC)
    requested_at = (
        (now - timedelta(days=requested_days_ago)).isoformat()
        if requested_days_ago is not None
        else None
    )
    sb.table("profiles").rows.append(
        {
            "id": user_id,
            "username": username,
            "display_name": "Tester",
            "data_deletion_requested_at": requested_at,
            "deletion_grace_notified_at": now.isoformat() if notified else None,
        }
    )
    sb.auth.admin._users[user_id] = {"email": email}


# ----- Notification phase ---------------------------------------------------


@pytest.mark.asyncio
async def test_notification_sends_email_and_stamps_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sb = FakeSupabase()
    _seed_user(sb, user_id="u1", requested_days_ago=1, notified=False)

    sent: list[dict[str, Any]] = []

    async def fake_send(**kwargs: Any) -> Any:
        sent.append(kwargs)
        return None

    monkeypatch.setattr(svc, "send_email", fake_send)

    result = await send_pending_grace_notifications(supabase=sb)  # type: ignore[arg-type]

    assert result == {"notified": 1, "failed": 0}
    assert len(sent) == 1
    call = sent[0]
    assert call["template"] == "account_deletion_grace_started"
    assert call["to_email"] == "u@example.com"
    assert call["idempotency_key"] == "email:account_deletion_grace_started:u1"
    assert "delete_on" in call["variables"]
    assert "app_url" in call["variables"]
    # Profile is stamped so the next tick won't re-fire.
    profile = sb.table("profiles").rows[0]
    assert profile["deletion_grace_notified_at"] is not None


@pytest.mark.asyncio
async def test_notification_skips_users_already_notified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sb = FakeSupabase()
    _seed_user(sb, user_id="u1", requested_days_ago=1, notified=True)

    sent: list[Any] = []

    async def fake_send(**kwargs: Any) -> Any:
        sent.append(kwargs)
        return None

    monkeypatch.setattr(svc, "send_email", fake_send)

    result = await send_pending_grace_notifications(supabase=sb)  # type: ignore[arg-type]

    assert result == {"notified": 0, "failed": 0}
    assert sent == []


@pytest.mark.asyncio
async def test_notification_ignores_users_without_pending_deletion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sb = FakeSupabase()
    _seed_user(sb, user_id="u1", requested_days_ago=None, notified=False)

    sent: list[Any] = []

    async def fake_send(**kwargs: Any) -> Any:
        sent.append(kwargs)
        return None

    monkeypatch.setattr(svc, "send_email", fake_send)

    result = await send_pending_grace_notifications(supabase=sb)  # type: ignore[arg-type]

    assert result == {"notified": 0, "failed": 0}
    assert sent == []


@pytest.mark.asyncio
async def test_notification_handles_send_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sb = FakeSupabase()
    _seed_user(sb, user_id="u1", requested_days_ago=1, notified=False)

    async def boom(**_kw: Any) -> Any:
        raise RuntimeError("resend out")

    monkeypatch.setattr(svc, "send_email", boom)

    result = await send_pending_grace_notifications(supabase=sb)  # type: ignore[arg-type]

    assert result == {"notified": 0, "failed": 1}
    # Profile was NOT stamped — next tick will retry.
    assert sb.table("profiles").rows[0]["deletion_grace_notified_at"] is None


@pytest.mark.asyncio
async def test_notification_skips_users_without_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sb = FakeSupabase()
    _seed_user(sb, user_id="u1", requested_days_ago=1, notified=False, email="")

    sent: list[Any] = []

    async def fake_send(**kwargs: Any) -> Any:
        sent.append(kwargs)
        return None

    monkeypatch.setattr(svc, "send_email", fake_send)

    result = await send_pending_grace_notifications(supabase=sb)  # type: ignore[arg-type]

    # No email → no send, but not counted as failed either.
    assert result == {"notified": 0, "failed": 0}
    assert sent == []


# ----- Hard-delete phase ----------------------------------------------------


@pytest.mark.asyncio
async def test_sweep_ignores_users_still_in_grace() -> None:
    sb = FakeSupabase()
    _seed_user(sb, user_id="u1", requested_days_ago=10, notified=True)

    result = await sweep_due_deletions(supabase=sb)  # type: ignore[arg-type]

    assert result == {"candidates": 0, "deleted": 0, "failed": 0}
    assert sb.auth.admin.deleted == []


@pytest.mark.asyncio
async def test_sweep_deletes_users_past_grace_and_audits_first() -> None:
    sb = FakeSupabase()
    _seed_user(sb, user_id="u1", requested_days_ago=31, notified=True)

    result = await sweep_due_deletions(supabase=sb)  # type: ignore[arg-type]

    assert result == {"candidates": 1, "deleted": 1, "failed": 0}
    assert sb.auth.admin.deleted == ["u1"]
    audit = sb.table("audit_log").rows
    assert len(audit) == 1
    assert audit[0]["action"] == "account_hard_deleted"
    assert audit[0]["entity_type"] == "profile"
    assert audit[0]["entity_id"] == "u1"
    assert audit[0]["metadata"]["grace_period_days"] == GRACE_PERIOD.days


@pytest.mark.asyncio
async def test_sweep_marks_failure_when_delete_user_raises() -> None:
    sb = FakeSupabase()
    _seed_user(sb, user_id="u1", requested_days_ago=31, notified=True)
    sb.auth.admin.delete_should_fail.add("u1")

    result = await sweep_due_deletions(supabase=sb)  # type: ignore[arg-type]

    assert result == {"candidates": 1, "deleted": 0, "failed": 1}
    # Audit row was written before the failed delete (per privacy policy
    # we keep the deletion-attempt trail).
    audit = sb.table("audit_log").rows
    assert len(audit) == 1
    assert sb.auth.admin.deleted == []


@pytest.mark.asyncio
async def test_sweep_respects_explicit_now() -> None:
    sb = FakeSupabase()
    # Requested 10 days ago in absolute terms, but we tell the sweep
    # that "now" is 60 days later — so the user IS past grace.
    _seed_user(sb, user_id="u1", requested_days_ago=10, notified=True)
    later = datetime.now(UTC) + timedelta(days=60)

    result = await sweep_due_deletions(now=later, supabase=sb)  # type: ignore[arg-type]

    assert result == {"candidates": 1, "deleted": 1, "failed": 0}


@pytest.mark.asyncio
async def test_sweep_ignores_users_who_never_requested() -> None:
    sb = FakeSupabase()
    _seed_user(sb, user_id="u1", requested_days_ago=None, notified=False)

    result = await sweep_due_deletions(supabase=sb)  # type: ignore[arg-type]

    assert result == {"candidates": 0, "deleted": 0, "failed": 0}


# ----- Combined run --------------------------------------------------------


@pytest.mark.asyncio
async def test_run_once_combines_both_phases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sb = FakeSupabase()
    # u1: just requested → needs notification, NOT due for delete.
    _seed_user(sb, user_id="u1", requested_days_ago=0.1, notified=False)
    # u2: already notified, past grace → should be deleted.
    _seed_user(sb, user_id="u2", requested_days_ago=31, notified=True)
    # u3: not requested → ignored.
    _seed_user(sb, user_id="u3", requested_days_ago=None, notified=False)

    sent: list[Any] = []

    async def fake_send(**kwargs: Any) -> Any:
        sent.append(kwargs)
        return None

    monkeypatch.setattr(svc, "send_email", fake_send)

    result = await run_once(supabase=sb)  # type: ignore[arg-type]

    assert result["notified"] == 1
    assert result["deleted"] == 1
    assert result["candidates"] == 1
    assert result["notify_failed"] == 0
    assert result["delete_failed"] == 0
    assert sb.auth.admin.deleted == ["u2"]
    # u1 got the email; u2 did not (already notified); u3 didn't qualify.
    sent_users = {call.get("user_id") for call in sent}
    assert sent_users == {"u1"}
