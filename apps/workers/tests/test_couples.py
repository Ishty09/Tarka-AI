"""Couples shared-session tests."""

from __future__ import annotations

from typing import Any

import pytest

from app.services.couples import (
    MEDIATOR_PERSONA_SLUG,
    CoupleLinkNotActiveError,
    CoupleLinkNotFoundError,
    NotALinkMemberError,
    start_couple_session,
)


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
        self._order_desc = False

    def select(self, _cols: str = "*") -> "_Query":
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, val))
        return self

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
            for col, val in self._filters:
                rows = [r for r in rows if r.get(col) == val]
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

    def seed_mediator(self) -> str:
        self.table("personas").rows.append(
            {"id": "mediator-id", "slug": MEDIATOR_PERSONA_SLUG, "name": "The Therapist"}
        )
        return "mediator-id"

    def seed_link(
        self,
        *,
        link_id: str = "link-1",
        user_a: str = "user-a",
        user_b: str = "user-b",
        status: str = "active",
    ) -> None:
        self.table("couple_links").rows.append(
            {
                "id": link_id,
                "user_a": user_a,
                "user_b": user_b,
                "status": status,
            }
        )


# ----- start_couple_session -------------------------------------------------


async def test_start_creates_new_conversation_for_user_a() -> None:
    sb = FakeSupabase()
    sb.seed_mediator()
    sb.seed_link()

    session = await start_couple_session(
        sb,  # type: ignore[arg-type]
        user_id="user-a",
        link_id="link-1",
    )

    assert session.link_id == "link-1"
    assert session.conversation_id  # uuid
    convo = sb.table("conversations").rows[0]
    assert convo["mode"] == "mediate"
    assert convo["couple_link_id"] == "link-1"
    assert convo["user_id"] == "user-a"
    assert convo["persona_id"] == "mediator-id"
    assert convo["metadata"]["persona_slug"] == MEDIATOR_PERSONA_SLUG


async def test_start_user_b_returns_same_conversation_as_user_a() -> None:
    """Both partners must land on the same conversation row."""

    sb = FakeSupabase()
    sb.seed_mediator()
    sb.seed_link()

    first = await start_couple_session(
        sb,  # type: ignore[arg-type]
        user_id="user-a",
        link_id="link-1",
    )
    second = await start_couple_session(
        sb,  # type: ignore[arg-type]
        user_id="user-b",
        link_id="link-1",
    )

    assert first.conversation_id == second.conversation_id
    # Only one conversation row created.
    assert len(sb.table("conversations").rows) == 1


async def test_start_archived_conversation_creates_new_one() -> None:
    """If the existing conversation got archived, we open a fresh one."""

    sb = FakeSupabase()
    sb.seed_mediator()
    sb.seed_link()
    # Pre-existing archived row for this link.
    sb.table("conversations").rows.append(
        {
            "id": "old-archived",
            "user_id": "user-a",
            "persona_id": "mediator-id",
            "mode": "mediate",
            "couple_link_id": "link-1",
            "archived": True,
        }
    )

    session = await start_couple_session(
        sb,  # type: ignore[arg-type]
        user_id="user-a",
        link_id="link-1",
    )

    assert session.conversation_id != "old-archived"


async def test_start_raises_when_link_missing() -> None:
    sb = FakeSupabase()
    sb.seed_mediator()
    with pytest.raises(CoupleLinkNotFoundError):
        await start_couple_session(
            sb,  # type: ignore[arg-type]
            user_id="user-a",
            link_id="ghost",
        )


async def test_start_raises_when_caller_not_a_member() -> None:
    sb = FakeSupabase()
    sb.seed_mediator()
    sb.seed_link()
    with pytest.raises(NotALinkMemberError):
        await start_couple_session(
            sb,  # type: ignore[arg-type]
            user_id="someone-else",
            link_id="link-1",
        )


async def test_start_raises_when_link_pending() -> None:
    sb = FakeSupabase()
    sb.seed_mediator()
    sb.seed_link(status="pending")
    with pytest.raises(CoupleLinkNotActiveError):
        await start_couple_session(
            sb,  # type: ignore[arg-type]
            user_id="user-a",
            link_id="link-1",
        )


async def test_start_raises_when_link_revoked() -> None:
    sb = FakeSupabase()
    sb.seed_mediator()
    sb.seed_link(status="revoked")
    with pytest.raises(CoupleLinkNotActiveError):
        await start_couple_session(
            sb,  # type: ignore[arg-type]
            user_id="user-a",
            link_id="link-1",
        )
