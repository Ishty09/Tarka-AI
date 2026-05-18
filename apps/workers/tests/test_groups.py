"""Group rooms shared-session + turn-taking tests."""

from __future__ import annotations

from typing import Any

import pytest

from app.services.groups import (
    AI_TURN_TAKING_THRESHOLD,
    GroupArchivedError,
    GroupNotFoundError,
    NotAGroupMemberError,
    count_recent_consecutive_humans,
    start_group_session,
)


MEDIATOR_PERSONA_ID = "persona-mediator"


class _Res:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, table: "_Table", op: str, payload: Any = None) -> None:
        self._table = table
        self._op = op
        self._payload = payload
        self._filters: list[tuple[str, Any]] = []
        self._limit: int | None = None
        self._maybe_single = False
        self._desc = False
        self._order_col: str | None = None

    def select(self, _cols: str = "*") -> "_Query":
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, val))
        return self

    def order(self, col: str, desc: bool = False) -> "_Query":
        self._order_col = col
        self._desc = desc
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
            for col, val in self._filters:
                rows = [r for r in rows if r.get(col) == val]
            if self._order_col is not None:
                rows.sort(
                    key=lambda r: r.get(self._order_col) or "",
                    reverse=self._desc,
                )
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
                self._table.rows.append(new_row)
                inserted.append(new_row)
            return _Res(inserted)

        return _Res([])


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

    def seed_group(
        self,
        *,
        group_id: str = "group-1",
        owner_id: str = "owner",
        archived: bool = False,
        members: list[str] | None = None,
    ) -> None:
        self.table("group_rooms").rows.append(
            {
                "id": group_id,
                "owner_id": owner_id,
                "mediator_persona_id": MEDIATOR_PERSONA_ID,
                "archived": archived,
            }
        )
        for user_id in (members or [owner_id]):
            self.table("group_members").rows.append(
                {"group_id": group_id, "user_id": user_id, "role": "owner" if user_id == owner_id else "member"}
            )


# ----- start_group_session --------------------------------------------------


async def test_start_creates_new_conversation_for_owner() -> None:
    sb = FakeSupabase()
    sb.seed_group(members=["owner", "member-1"])

    session = await start_group_session(
        sb,  # type: ignore[arg-type]
        user_id="owner",
        group_id="group-1",
    )

    assert session.conversation_id  # uuid
    assert session.mediator_persona_id == MEDIATOR_PERSONA_ID
    assert set(session.member_ids) == {"owner", "member-1"}
    convo = sb.table("conversations").rows[0]
    assert convo["mode"] == "mediate"
    assert convo["group_room_id"] == "group-1"
    assert convo["user_id"] == "owner"
    assert convo["persona_id"] == MEDIATOR_PERSONA_ID


async def test_start_any_member_returns_same_conversation() -> None:
    sb = FakeSupabase()
    sb.seed_group(members=["owner", "alice", "bob"])

    first = await start_group_session(sb, user_id="owner", group_id="group-1")  # type: ignore[arg-type]
    second = await start_group_session(sb, user_id="alice", group_id="group-1")  # type: ignore[arg-type]
    third = await start_group_session(sb, user_id="bob", group_id="group-1")  # type: ignore[arg-type]

    assert first.conversation_id == second.conversation_id == third.conversation_id
    assert len(sb.table("conversations").rows) == 1


async def test_start_archived_room_raises() -> None:
    sb = FakeSupabase()
    sb.seed_group(archived=True)
    with pytest.raises(GroupArchivedError):
        await start_group_session(sb, user_id="owner", group_id="group-1")  # type: ignore[arg-type]


async def test_start_not_a_member_raises() -> None:
    sb = FakeSupabase()
    sb.seed_group(members=["owner"])
    with pytest.raises(NotAGroupMemberError):
        await start_group_session(
            sb,  # type: ignore[arg-type]
            user_id="random",
            group_id="group-1",
        )


async def test_start_missing_room_raises() -> None:
    sb = FakeSupabase()
    with pytest.raises(GroupNotFoundError):
        await start_group_session(
            sb,  # type: ignore[arg-type]
            user_id="owner",
            group_id="ghost",
        )


# ----- count_recent_consecutive_humans -------------------------------------


async def test_count_returns_zero_when_empty() -> None:
    sb = FakeSupabase()
    streak = await count_recent_consecutive_humans(
        sb,  # type: ignore[arg-type]
        conversation_id="convo",
    )
    assert streak == 0


async def test_count_returns_three_for_three_humans_in_a_row() -> None:
    sb = FakeSupabase()
    # Order matters: newest first when reversed by created_at desc.
    rows = [
        {"id": 1, "role": "user", "conversation_id": "convo", "created_at": "2026-05-19T00:00:01Z"},
        {"id": 2, "role": "user", "conversation_id": "convo", "created_at": "2026-05-19T00:00:02Z"},
        {"id": 3, "role": "user", "conversation_id": "convo", "created_at": "2026-05-19T00:00:03Z"},
    ]
    sb.table("messages").rows.extend(rows)
    streak = await count_recent_consecutive_humans(
        sb,  # type: ignore[arg-type]
        conversation_id="convo",
    )
    assert streak == 3
    assert streak >= AI_TURN_TAKING_THRESHOLD


async def test_count_resets_after_assistant_message() -> None:
    sb = FakeSupabase()
    rows = [
        {"id": 1, "role": "user", "conversation_id": "convo", "created_at": "2026-05-19T00:00:01Z"},
        {"id": 2, "role": "user", "conversation_id": "convo", "created_at": "2026-05-19T00:00:02Z"},
        {"id": 3, "role": "assistant", "conversation_id": "convo", "created_at": "2026-05-19T00:00:03Z"},
        {"id": 4, "role": "user", "conversation_id": "convo", "created_at": "2026-05-19T00:00:04Z"},
    ]
    sb.table("messages").rows.extend(rows)
    streak = await count_recent_consecutive_humans(
        sb,  # type: ignore[arg-type]
        conversation_id="convo",
    )
    # Last message back: user (4), then assistant (3) — streak stops at 1.
    assert streak == 1


async def test_count_ignores_other_conversations() -> None:
    sb = FakeSupabase()
    sb.table("messages").rows.extend([
        {"id": 1, "role": "user", "conversation_id": "other", "created_at": "2026-05-19T00:00:01Z"},
        {"id": 2, "role": "user", "conversation_id": "other", "created_at": "2026-05-19T00:00:02Z"},
        {"id": 3, "role": "user", "conversation_id": "other", "created_at": "2026-05-19T00:00:03Z"},
    ])
    streak = await count_recent_consecutive_humans(
        sb,  # type: ignore[arg-type]
        conversation_id="convo",
    )
    assert streak == 0
