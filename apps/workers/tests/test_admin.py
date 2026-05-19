"""Admin service: auth gate + listings + moderation mutations."""

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

from app.services.admin import (
    NotAdminError,
    list_incidents,
    list_pending_feed_posts,
    list_pending_personas,
    moderate_feed_post,
    moderate_persona,
    require_admin,
    review_incident,
    search_users,
    suspend_user,
    unsuspend_user,
)

# ----- Fakes ---------------------------------------------------------------


class _Res:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Q:
    def __init__(self, table: _Table, op: str, payload: Any = None) -> None:
        self._t = table
        self._op = op
        self._payload = payload
        self._filters: list[tuple[str, str, Any]] = []
        self._or: list[str] | None = None
        self._limit: int | None = None
        self._maybe_single = False

    def select(self, _cols: str = "*") -> _Q:
        return self

    def update(self, payload: dict[str, Any]) -> _Q:
        return _Q(self._t, "update", payload).eq_carry(self)

    def insert(self, payload: Any) -> _Q:
        return _Q(self._t, "insert", payload)

    def eq_carry(self, src: _Q) -> _Q:
        self._filters = list(src._filters)
        return self

    def eq(self, col: str, val: Any) -> _Q:
        self._filters.append((col, "eq", val))
        return self

    def in_(self, col: str, vals: list[Any]) -> _Q:
        self._filters.append((col, "in", vals))
        return self

    def is_(self, col: str, val: Any) -> _Q:
        # 'null' string mimics postgrest filter param
        self._filters.append((col, "is", val))
        return self

    def or_(self, expr: str) -> _Q:
        self._or = expr.split(",")
        return self

    def order(self, _col: str, desc: bool = False) -> _Q:
        return self

    def limit(self, n: int) -> _Q:
        self._limit = n
        return self

    def maybe_single(self) -> _Q:
        self._maybe_single = True
        return self

    def _filter_row(self, row: dict[str, Any]) -> bool:
        for col, op, val in self._filters:
            v = row.get(col)
            if op == "eq" and v != val:
                return False
            if op == "in" and v not in val:
                return False
            if op == "is" and val == "null" and v is not None:
                return False
        if self._or:
            ok = False
            for clause in self._or:
                col, op, val = clause.split(".", 2)
                if op == "ilike":
                    needle = val.strip("%").lower()
                    candidate = row.get(col)
                    if isinstance(candidate, str) and needle in candidate.lower():
                        ok = True
                        break
            if not ok:
                return False
        return True

    async def execute(self) -> _Res:
        if self._op == "select":
            rows = [r for r in self._t.rows if self._filter_row(r)]
            if self._limit is not None:
                rows = rows[: self._limit]
            if self._maybe_single:
                return _Res(rows[0] if rows else None)
            return _Res(rows)

        if self._op == "update":
            for r in self._t.rows:
                if self._filter_row(r):
                    r.update(self._payload)
            return _Res(None)

        if self._op == "insert":
            payloads = self._payload if isinstance(self._payload, list) else [self._payload]
            for p in payloads:
                row = dict(p)
                if "id" not in row and self._t.name == "audit_log":
                    row["id"] = len(self._t.rows) + 1
                self._t.rows.append(row)
            return _Res(payloads)

        raise AssertionError(self._op)


class _Table:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, _cols: str = "*") -> _Q:
        return _Q(self, "select")

    def insert(self, payload: Any) -> _Q:
        return _Q(self, "insert", payload)

    def update(self, payload: dict[str, Any]) -> _Q:
        return _Q(self, "update", payload)


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, _Table] = {}

    def table(self, name: str) -> _Table:
        self.tables.setdefault(name, _Table(name))
        return self.tables[name]


# ----- Tests ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_admin_rejects_non_admin() -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.append({"id": "u1", "is_admin": False})
    with pytest.raises(NotAdminError):
        await require_admin(sb, user_id="u1")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_require_admin_accepts_admin() -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.append({"id": "u1", "is_admin": True})
    actor = await require_admin(sb, user_id="u1")  # type: ignore[arg-type]
    assert actor.user_id == "u1"


@pytest.mark.asyncio
async def test_list_pending_personas() -> None:
    sb = FakeSupabase()
    sb.table("personas").rows.extend(
        [
            {
                "id": "p1",
                "slug": "x",
                "name": "X",
                "owner_id": "u",
                "category": "argue",
                "visibility": "public",
                "moderation_status": "pending",
                "system_prompt": "sp",
                "created_at": "2026-05-19",
            },
            {
                "id": "p2",
                "slug": "y",
                "name": "Y",
                "owner_id": "u",
                "category": "roast",
                "visibility": "public",
                "moderation_status": "approved",
                "system_prompt": "sp",
                "created_at": "2026-05-18",
            },
        ]
    )
    out = await list_pending_personas(sb)  # type: ignore[arg-type]
    assert [r.id for r in out] == ["p1"]


@pytest.mark.asyncio
async def test_moderate_persona_writes_audit() -> None:
    sb = FakeSupabase()
    sb.table("personas").rows.append(
        {"id": "p1", "moderation_status": "pending", "is_safe": False}
    )
    sb.table("profiles").rows.append({"id": "admin", "is_admin": True})
    actor = await require_admin(sb, user_id="admin")  # type: ignore[arg-type]

    await moderate_persona(
        sb, actor=actor, persona_id="p1", action="approve", notes="Looks fine."  # type: ignore[arg-type]
    )

    persona = sb.tables["personas"].rows[0]
    assert persona["moderation_status"] == "approved"
    assert persona["is_safe"] is True
    audits = sb.tables["audit_log"].rows
    assert len(audits) == 1
    assert audits[0]["action"] == "persona_approve"
    assert audits[0]["entity_id"] == "p1"
    assert audits[0]["actor_user_id"] == "admin"


@pytest.mark.asyncio
async def test_moderate_feed_post_reject_takes_down() -> None:
    sb = FakeSupabase()
    sb.table("roast_feed_posts").rows.append(
        {"id": "fp1", "moderation_status": "pending", "visibility": "public", "is_safe": True}
    )
    sb.table("profiles").rows.append({"id": "admin", "is_admin": True})
    actor = await require_admin(sb, user_id="admin")  # type: ignore[arg-type]

    await moderate_feed_post(
        sb, actor=actor, post_id="fp1", action="reject"  # type: ignore[arg-type]
    )

    post = sb.tables["roast_feed_posts"].rows[0]
    assert post["moderation_status"] == "rejected"
    assert post["visibility"] == "removed"
    assert post["is_safe"] is False


@pytest.mark.asyncio
async def test_suspend_and_unsuspend_user() -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.extend(
        [
            {"id": "admin", "is_admin": True, "is_suspended": False},
            {"id": "target", "is_admin": False, "is_suspended": False},
        ]
    )
    actor = await require_admin(sb, user_id="admin")  # type: ignore[arg-type]

    await suspend_user(sb, actor=actor, user_id="target", reason="Spam")  # type: ignore[arg-type]
    target = next(r for r in sb.tables["profiles"].rows if r["id"] == "target")
    assert target["is_suspended"] is True
    assert target["suspension_reason"] == "Spam"

    await unsuspend_user(sb, actor=actor, user_id="target")  # type: ignore[arg-type]
    target = next(r for r in sb.tables["profiles"].rows if r["id"] == "target")
    assert target["is_suspended"] is False
    assert target["suspension_reason"] is None

    audits = sb.tables["audit_log"].rows
    assert {a["action"] for a in audits} == {"user_suspended", "user_unsuspended"}


@pytest.mark.asyncio
async def test_suspend_self_blocked() -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.append({"id": "admin", "is_admin": True})
    actor = await require_admin(sb, user_id="admin")  # type: ignore[arg-type]
    with pytest.raises(PermissionError):
        await suspend_user(sb, actor=actor, user_id="admin", reason="oops")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_review_incident_marks_reviewed_by_and_at() -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.append({"id": "admin", "is_admin": True})
    sb.table("safety_incidents").rows.append(
        {
            "id": 7,
            "user_id": "u1",
            "category": "crisis",
            "verdict": "crisis",
            "action_taken": "blocked",
            "reviewed_by": None,
            "reviewed_at": None,
            "created_at": "2026-05-19",
        }
    )
    actor = await require_admin(sb, user_id="admin")  # type: ignore[arg-type]

    await review_incident(
        sb, actor=actor, incident_id=7, notes="Followed up by hand."  # type: ignore[arg-type]
    )

    incident = sb.tables["safety_incidents"].rows[0]
    assert incident["reviewed_by"] == "admin"
    assert incident["reviewed_at"] is not None
    assert sb.tables["audit_log"].rows[0]["action"] == "incident_reviewed"


@pytest.mark.asyncio
async def test_list_incidents_unreviewed_only() -> None:
    sb = FakeSupabase()
    sb.table("safety_incidents").rows.extend(
        [
            {
                "id": 1,
                "user_id": "u",
                "conversation_id": None,
                "message_id": None,
                "category": "crisis",
                "verdict": "crisis",
                "action_taken": "x",
                "reviewed_by": None,
                "reviewed_at": None,
                "created_at": "2026-05-19",
            },
            {
                "id": 2,
                "user_id": "u",
                "conversation_id": None,
                "message_id": None,
                "category": "spam",
                "verdict": "spam",
                "action_taken": "x",
                "reviewed_by": "admin",
                "reviewed_at": "2026-05-18",
                "created_at": "2026-05-18",
            },
        ]
    )
    out = await list_incidents(sb)  # type: ignore[arg-type]
    assert [r.id for r in out] == [1]


@pytest.mark.asyncio
async def test_search_users_ilike() -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.extend(
        [
            {
                "id": "u1",
                "username": "rabbi",
                "display_name": "Rabbi",
                "tier": "max",
                "is_admin": True,
                "is_suspended": False,
                "suspension_reason": None,
                "created_at": "2026-01-01",
                "data_deletion_requested_at": None,
            },
            {
                "id": "u2",
                "username": "alice",
                "display_name": None,
                "tier": "free",
                "is_admin": False,
                "is_suspended": False,
                "suspension_reason": None,
                "created_at": "2026-02-01",
                "data_deletion_requested_at": None,
            },
        ]
    )
    out = await search_users(sb, query="ALI")  # type: ignore[arg-type]
    assert [r.username for r in out] == ["alice"]


@pytest.mark.asyncio
async def test_list_pending_feed_posts() -> None:
    sb = FakeSupabase()
    sb.table("roast_feed_posts").rows.extend(
        [
            {
                "id": "fp1",
                "user_id": "u",
                "conversation_id": "c",
                "message_id": 1,
                "caption": "ouch",
                "moderation_status": "pending",
                "visibility": "public",
                "created_at": "2026-05-19",
            },
            {
                "id": "fp2",
                "user_id": "u",
                "conversation_id": "c",
                "message_id": 2,
                "caption": None,
                "moderation_status": "approved",
                "visibility": "public",
                "created_at": "2026-05-18",
            },
        ]
    )
    out = await list_pending_feed_posts(sb)  # type: ignore[arg-type]
    assert [r.id for r in out] == ["fp1"]
