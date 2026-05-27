"""safety_incidents service: insert + crisis-escalation email."""

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

from app.services import safety_incidents as si_mod
from app.services.safety_incidents import (
    CRISIS_THRESHOLD,
    CRISIS_WINDOW,
    record_incident,
)


# ----- Fake supabase -------------------------------------------------------


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

    def insert(self, payload: Any) -> "_Query":
        return _Query(self._table, "insert", payload)

    def eq(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, "eq", val))
        return self

    def gte(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, "gte", val))
        return self

    def limit(self, n: int) -> "_Query":
        self._limit = n
        return self

    def maybe_single(self) -> "_Query":
        self._maybe_single = True
        return self

    async def execute(self) -> _Res:
        if self._op == "insert":
            row = (
                dict(self._payload)
                if isinstance(self._payload, dict)
                else self._payload
            )
            row.setdefault("created_at", datetime.now(UTC).isoformat())
            self._table.rows.append(row)
            return _Res([row])

        rows = [
            r
            for r in self._table.rows
            if all(
                (op == "eq" and r.get(col) == val)
                or (op == "gte" and (r.get(col) or "") >= val)
                for col, op, val in self._filters
            )
        ]
        if self._limit is not None:
            rows = rows[: self._limit]
        if self._maybe_single:
            return _Res(rows[0] if rows else None)
        return _Res(rows)


class _Table:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, cols: str = "*") -> _Query:
        return _Query(self, "select").select(cols)

    def insert(self, payload: Any) -> _Query:
        return _Query(self, "insert", payload)


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, _Table] = {}

    def table(self, name: str) -> _Table:
        if name not in self.tables:
            self.tables[name] = _Table()
        return self.tables[name]


# ----- Helpers -------------------------------------------------------------


def _seed_profile(
    sb: FakeSupabase,
    *,
    user_id: str = "u",
    contact_email: str | None = "trusted@example.test",
    display_name: str | None = "Rabbi",
) -> None:
    sb.table("profiles").rows.append(
        {
            "id": user_id,
            "display_name": display_name,
            "username": "rabbi",
            "emergency_contact_name": "Friend" if contact_email else None,
            "emergency_contact_email": contact_email,
        }
    )


# ----- Tests --------------------------------------------------------------


async def test_records_safety_incident_for_non_crisis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """jailbreak/abuse/etc. write the audit row but never escalate."""

    sb = FakeSupabase()
    _seed_profile(sb)

    emails: list[dict[str, Any]] = []

    async def fake_email(**kwargs: Any) -> Any:
        emails.append(kwargs)
        return type("R", (), {"status": "sent"})()

    monkeypatch.setattr(si_mod, "send_email", fake_email)

    await record_incident(
        sb,  # type: ignore[arg-type]
        user_id="u",
        conversation_id="c",
        message_id=42,
        category="jailbreak",
        verdict_reason="DAN prompt detected",
    )

    rows = sb.table("safety_incidents").rows
    assert len(rows) == 1
    assert rows[0]["category"] == "jailbreak"
    assert rows[0]["user_id"] == "u"
    assert rows[0]["message_id"] == 42
    assert emails == []


async def test_first_crisis_inserts_but_does_not_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One crisis in 24h is below threshold — row written, no email."""

    sb = FakeSupabase()
    _seed_profile(sb)

    emails: list[dict[str, Any]] = []

    async def fake_email(**kwargs: Any) -> Any:
        emails.append(kwargs)
        return type("R", (), {"status": "sent"})()

    monkeypatch.setattr(si_mod, "send_email", fake_email)

    await record_incident(
        sb,  # type: ignore[arg-type]
        user_id="u",
        conversation_id="c",
        message_id=1,
        category="crisis",
        verdict_reason="suicidal ideation",
    )

    assert len(sb.table("safety_incidents").rows) == 1
    assert emails == []


async def test_second_crisis_within_24h_emails_contact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 2nd crisis within the 24h window fires the email exactly once,
    addressed to the user's listed emergency contact, with their
    display_name substituted into the body.
    """

    sb = FakeSupabase()
    _seed_profile(sb)
    # Seed a prior crisis 2 hours ago.
    sb.table("safety_incidents").rows.append(
        {
            "user_id": "u",
            "category": "crisis",
            "created_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
        }
    )

    emails: list[dict[str, Any]] = []

    async def fake_email(**kwargs: Any) -> Any:
        emails.append(kwargs)
        return type("R", (), {"status": "sent"})()

    monkeypatch.setattr(si_mod, "send_email", fake_email)

    await record_incident(
        sb,  # type: ignore[arg-type]
        user_id="u",
        conversation_id="c",
        message_id=2,
        category="crisis",
        verdict_reason="self-harm intent",
    )

    assert len(emails) == 1
    call = emails[0]
    assert call["template"] == "emergency_contact_notification"
    assert call["to_email"] == "trusted@example.test"
    assert call["variables"] == {"user_display_name": "Rabbi"}
    assert call["user_id"] == "u"
    # Idempotency keyed on (user_id, UTC date) — a third crisis the
    # same day would dedupe to no extra send.
    assert call["idempotency_key"].startswith(
        "email:emergency_contact_notification:u:"
    )


async def test_crisis_older_than_window_does_not_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A crisis from 25h ago is outside the 24h window and shouldn't
    push the count over the threshold. The new crisis is the only one
    in-window → no escalation.
    """

    sb = FakeSupabase()
    _seed_profile(sb)
    older = datetime.now(UTC) - CRISIS_WINDOW - timedelta(hours=1)
    sb.table("safety_incidents").rows.append(
        {"user_id": "u", "category": "crisis", "created_at": older.isoformat()}
    )

    emails: list[dict[str, Any]] = []

    async def fake_email(**kwargs: Any) -> Any:
        emails.append(kwargs)
        return type("R", (), {"status": "sent"})()

    monkeypatch.setattr(si_mod, "send_email", fake_email)

    await record_incident(
        sb,  # type: ignore[arg-type]
        user_id="u",
        conversation_id="c",
        message_id=3,
        category="crisis",
        verdict_reason="ideation",
    )

    assert emails == []


async def test_no_contact_listed_skips_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User didn't list an emergency contact at onboarding. The 2nd
    crisis still writes the audit row but the email is a clean no-op —
    hotlines surface via the refusal stream separately.
    """

    sb = FakeSupabase()
    _seed_profile(sb, contact_email=None)
    sb.table("safety_incidents").rows.append(
        {
            "user_id": "u",
            "category": "crisis",
            "created_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
        }
    )

    emails: list[dict[str, Any]] = []

    async def fake_email(**kwargs: Any) -> Any:
        emails.append(kwargs)
        return type("R", (), {"status": "sent"})()

    monkeypatch.setattr(si_mod, "send_email", fake_email)

    await record_incident(
        sb,  # type: ignore[arg-type]
        user_id="u",
        conversation_id="c",
        message_id=4,
        category="crisis",
        verdict_reason="ideation",
    )

    assert len(sb.table("safety_incidents").rows) == 2
    assert emails == []


def test_threshold_constants() -> None:
    """Lock the §13 promise — 2 crises in 24h — at the constant level
    so a future change is a deliberate, reviewable edit.
    """

    assert CRISIS_THRESHOLD == 2
    assert CRISIS_WINDOW == timedelta(hours=24)
