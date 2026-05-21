"""Data-export pipeline tests (§27 step 57).

The service touches a lot of supabase surface (10+ tables, storage, auth
admin), so we build a focused stub that captures the calls we care about
rather than reuse the per-test Fakes that lived alongside other
services. Each test asserts on either the persisted state, the storage
contents, or the email call.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.services import data_export as svc
from app.services.data_export import (
    EXPORT_BUCKET,
    USER_SCOPED_TABLES,
    ExportResult,
    claim_next_pending,
    gather_export,
    process_request,
    run_pending_batch,
    serialise,
)

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
        self._not_filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None
        self._order_col: str | None = None
        self._order_desc = False
        self._maybe_single = False
        self._cols: list[str] | None = None

    def select(self, cols: str = "*") -> _Query:
        # Track requested columns so push_subscriptions etc. can be
        # filtered. "*" means "everything".
        if cols and cols != "*":
            self._cols = [c.strip() for c in cols.split(",") if c.strip()]
        return self

    def eq(self, col: str, val: Any) -> _Query:
        self._filters.append((col, "eq", val))
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

    def maybe_single(self) -> _Query:
        self._maybe_single = True
        return self

    def _matches(self, row: dict[str, Any]) -> bool:
        for col, op, val in self._filters:
            if op == "eq" and row.get(col) != val:
                return False
            if op == "in" and row.get(col) not in val:
                return False
        return True

    async def execute(self) -> _Res:
        rows = list(self._table.rows)

        if self._op == "select":
            filtered = [r for r in rows if self._matches(r)]
            if self._order_col is not None:
                filtered.sort(
                    key=lambda r: r.get(self._order_col) or "",
                    reverse=self._order_desc,
                )
            if self._limit is not None:
                filtered = filtered[: self._limit]
            if self._cols is not None:
                filtered = [
                    {k: v for k, v in r.items() if k in self._cols}
                    for r in filtered
                ]
            if self._maybe_single:
                return _Res(filtered[0] if filtered else None)
            return _Res(filtered)

        if self._op == "insert":
            payload = (
                self._payload if isinstance(self._payload, list) else [self._payload]
            )
            for row in payload:
                self._table.rows.append(dict(row))
            return _Res(payload)

        if self._op == "update":
            updates: list[dict[str, Any]] = []
            for r in self._table.rows:
                if self._matches(r):
                    r.update(self._payload)
                    updates.append(r)
            return _Res(updates)

        return _Res([])


class _Table:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, cols: str = "*") -> _Query:
        q = _Query(self, "select")
        return q.select(cols)

    def insert(self, payload: Any) -> _Query:
        return _Query(self, "insert", payload)

    def update(self, payload: dict[str, Any]) -> _Query:
        return _Query(self, "update", payload)


class _FakeBucket:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.signed_calls: list[tuple[str, int]] = []

    async def upload(
        self, *, path: str, file: bytes, file_options: dict[str, str] | None = None
    ) -> None:
        self.objects[path] = file

    async def create_signed_url(self, path: str, ttl: int) -> dict[str, str]:
        self.signed_calls.append((path, ttl))
        return {"signedURL": f"https://signed.example/{path}?ttl={ttl}"}


class _FakeStorage:
    def __init__(self) -> None:
        self.buckets: dict[str, _FakeBucket] = {}

    def from_(self, bucket: str) -> _FakeBucket:
        if bucket not in self.buckets:
            self.buckets[bucket] = _FakeBucket()
        return self.buckets[bucket]


class _FakeAdmin:
    def __init__(self, *, users: dict[str, dict[str, str]]) -> None:
        self._users = users

    async def get_user_by_id(self, user_id: str) -> Any:
        class _User:
            def __init__(self, email: str) -> None:
                self.email = email

        class _Resp:
            def __init__(self, email: str) -> None:
                self.user = _User(email)

        record = self._users.get(user_id, {"email": ""})
        return _Resp(record.get("email", ""))


class _FakeAuth:
    def __init__(self, *, users: dict[str, dict[str, str]]) -> None:
        self.admin = _FakeAdmin(users=users)


class FakeSupabase:
    def __init__(self, *, users: dict[str, dict[str, str]] | None = None) -> None:
        self.tables: dict[str, _Table] = {}
        self.storage = _FakeStorage()
        self.auth = _FakeAuth(users=users or {})

    def table(self, name: str) -> _Table:
        if name not in self.tables:
            self.tables[name] = _Table(name)
        return self.tables[name]


# ----- Seed helpers ---------------------------------------------------------


def _seed_minimal_user(sb: FakeSupabase, user_id: str, *, email: str) -> None:
    sb.tables.clear()
    sb.auth = _FakeAuth(users={user_id: {"email": email}})
    sb.table("profiles").rows.append(
        {"id": user_id, "display_name": "Test User", "username": "tester"}
    )
    sb.table("conversations").rows.append(
        {"id": "conv-1", "user_id": user_id, "mode": "argue"}
    )
    sb.table("messages").rows.append(
        {"id": 1, "conversation_id": "conv-1", "role": "user", "content": "hi"}
    )
    sb.table("user_facts").rows.append(
        {"id": 1, "user_id": user_id, "fact": "user said X"}
    )
    sb.table("push_subscriptions").rows.append(
        {
            "id": "push-1",
            "user_id": user_id,
            "token": "SECRET-TOKEN",
            "platform": "web",
        }
    )
    sb.table("couple_links").rows.extend(
        [
            {"id": "cl-1", "user_a": user_id, "user_b": "other"},
            {"id": "cl-2", "user_a": "other", "user_b": user_id},
            {"id": "cl-3", "user_a": "x", "user_b": "y"},
        ]
    )
    sb.table("group_members").rows.append(
        {"group_id": "g-1", "user_id": user_id, "role": "member"}
    )
    sb.table("wagers").rows.append({"id": "w-1", "user_id": user_id, "stake": 1000})
    sb.table("wager_checkins").rows.append(
        {"id": 1, "wager_id": "w-1", "user_id": user_id, "status": "completed"}
    )
    sb.table("roast_feed_votes").rows.append(
        {"post_id": "p-1", "user_id": user_id, "vote": 1}
    )


# ----- gather_export --------------------------------------------------------


@pytest.mark.asyncio
async def test_gather_export_returns_every_user_scoped_table() -> None:
    sb = FakeSupabase()
    _seed_minimal_user(sb, "u1", email="u1@example.com")

    payload, counts = await gather_export(sb, user_id="u1")  # type: ignore[arg-type]

    assert payload["schema_version"] == svc.SCHEMA_VERSION
    assert payload["user_id"] == "u1"
    # Profile shows up under its own key.
    assert payload["tables"]["profile"]["id"] == "u1"
    # Every USER_SCOPED_TABLES entry should be addressed.
    for table, _col in USER_SCOPED_TABLES:
        assert table in payload["tables"]
        assert table in counts
    # Messages were joined through conversations.
    assert payload["tables"]["messages"][0]["conversation_id"] == "conv-1"


@pytest.mark.asyncio
async def test_gather_export_redacts_push_tokens() -> None:
    sb = FakeSupabase()
    _seed_minimal_user(sb, "u1", email="u1@example.com")

    payload, _ = await gather_export(sb, user_id="u1")  # type: ignore[arg-type]

    push_rows = payload["tables"]["push_subscriptions"]
    assert len(push_rows) == 1
    assert "token" not in push_rows[0]
    assert push_rows[0]["platform"] == "web"


@pytest.mark.asyncio
async def test_gather_export_includes_both_sides_of_couple_links() -> None:
    sb = FakeSupabase()
    _seed_minimal_user(sb, "u1", email="u1@example.com")

    payload, _ = await gather_export(sb, user_id="u1")  # type: ignore[arg-type]

    couple_ids = {c["id"] for c in payload["tables"]["couple_links"]}
    # cl-1 (user is user_a) + cl-2 (user is user_b). cl-3 must not leak.
    assert couple_ids == {"cl-1", "cl-2"}


def test_serialise_emits_stable_json() -> None:
    blob = serialise({"b": 2, "a": 1})
    parsed = json.loads(blob)
    assert parsed == {"a": 1, "b": 2}
    # sort_keys keeps the diff stable across runs.
    assert blob.index(b'"a"') < blob.index(b'"b"')


# ----- claim_next_pending ---------------------------------------------------


@pytest.mark.asyncio
async def test_claim_next_pending_flips_status_atomically() -> None:
    sb = FakeSupabase()
    sb.table("data_export_requests").rows.extend(
        [
            {
                "id": "req-1",
                "user_id": "u1",
                "status": "pending",
                "requested_at": "2026-05-20T10:00:00+00:00",
            },
            {
                "id": "req-2",
                "user_id": "u2",
                "status": "pending",
                "requested_at": "2026-05-20T11:00:00+00:00",
            },
        ]
    )

    claimed = await claim_next_pending(sb)  # type: ignore[arg-type]

    assert claimed is not None
    assert claimed["id"] == "req-1"
    # The original row's status is now 'processing'.
    rows = sb.table("data_export_requests").rows
    assert next(r for r in rows if r["id"] == "req-1")["status"] == "processing"
    # req-2 is still pending.
    assert next(r for r in rows if r["id"] == "req-2")["status"] == "pending"


@pytest.mark.asyncio
async def test_claim_next_pending_returns_none_when_queue_empty() -> None:
    sb = FakeSupabase()
    sb.table("data_export_requests")  # ensure the table exists but is empty
    assert await claim_next_pending(sb) is None  # type: ignore[arg-type]


# ----- process_request ------------------------------------------------------


@pytest.mark.asyncio
async def test_process_request_uploads_signs_emails_and_marks_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sb = FakeSupabase()
    _seed_minimal_user(sb, "u1", email="u1@example.com")
    sb.table("data_export_requests").rows.append(
        {
            "id": "req-1",
            "user_id": "u1",
            "status": "processing",
            "requested_at": "2026-05-20T10:00:00+00:00",
            "started_at": "2026-05-20T10:00:01+00:00",
        }
    )

    sent: list[dict[str, Any]] = []

    async def fake_send(**kwargs: Any) -> Any:
        sent.append(kwargs)

        class R:
            status = "sent"

        return R()

    monkeypatch.setattr(svc, "send_email", fake_send)

    result = await process_request(
        request={"id": "req-1", "user_id": "u1"},
        supabase=sb,  # type: ignore[arg-type]
    )

    assert isinstance(result, ExportResult)
    assert result.status == "ready"
    # Blob was uploaded to the user-scoped path.
    bucket = sb.storage.from_(EXPORT_BUCKET)
    assert "u1/req-1.json" in bucket.objects
    # Signed URL was generated.
    assert bucket.signed_calls
    # data_export_requests row reflects readiness.
    row = next(r for r in sb.table("data_export_requests").rows if r["id"] == "req-1")
    assert row["status"] == "ready"
    assert row["storage_path"] == "u1/req-1.json"
    assert row["download_url"].startswith("https://signed.example/")
    assert isinstance(row["byte_size"], int)
    assert row["byte_size"] > 0
    assert row["email_sent_at"] is not None
    # Email was dispatched with the right template + idempotency key.
    assert len(sent) == 1
    call = sent[0]
    assert call["template"] == "data_export_ready"
    assert call["to_email"] == "u1@example.com"
    assert call["idempotency_key"] == "email:data_export_ready:req-1"
    assert "download_url" in call["variables"]
    assert call["variables"]["ttl_hours"] == svc.DOWNLOAD_TTL_HOURS


@pytest.mark.asyncio
async def test_process_request_marks_failed_on_storage_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sb = FakeSupabase()
    _seed_minimal_user(sb, "u1", email="u1@example.com")
    sb.table("data_export_requests").rows.append(
        {"id": "req-1", "user_id": "u1", "status": "processing"}
    )

    async def boom(*_args: Any, **_kw: Any) -> str:
        raise RuntimeError("bucket on fire")

    monkeypatch.setattr(svc, "upload_to_storage", boom)

    result = await process_request(
        request={"id": "req-1", "user_id": "u1"},
        supabase=sb,  # type: ignore[arg-type]
    )

    assert result.status == "failed"
    assert result.error is not None
    assert "bucket on fire" in result.error
    row = next(r for r in sb.table("data_export_requests").rows if r["id"] == "req-1")
    assert row["status"] == "failed"
    assert row["error_message"].startswith("bucket on fire")


@pytest.mark.asyncio
async def test_process_request_skips_email_when_user_has_no_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sb = FakeSupabase()
    _seed_minimal_user(sb, "u1", email="")  # auth.admin returns empty string

    sent: list[Any] = []

    async def fake_send(**kwargs: Any) -> Any:
        sent.append(kwargs)
        return None

    monkeypatch.setattr(svc, "send_email", fake_send)

    result = await process_request(
        request={"id": "req-1", "user_id": "u1"},
        supabase=sb,  # type: ignore[arg-type]
    )

    assert result.status == "ready"
    assert sent == []  # never sent — no email on file


# ----- run_pending_batch ----------------------------------------------------


@pytest.mark.asyncio
async def test_run_pending_batch_drains_up_to_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sb = FakeSupabase()
    _seed_minimal_user(sb, "u1", email="u1@example.com")
    base = datetime(2026, 5, 20, 10, 0, tzinfo=UTC)
    for i in range(3):
        sb.table("data_export_requests").rows.append(
            {
                "id": f"req-{i}",
                "user_id": "u1",
                "status": "pending",
                "requested_at": (base + timedelta(minutes=i)).isoformat(),
            }
        )

    async def fake_send(**_kw: Any) -> Any:
        class R:
            status = "sent"

        return R()

    monkeypatch.setattr(svc, "send_email", fake_send)

    result = await run_pending_batch(limit=2, supabase=sb)  # type: ignore[arg-type]

    assert result == {"processed": 2, "failed": 0}
    # Two became ready, one still pending.
    statuses = sorted(r["status"] for r in sb.table("data_export_requests").rows)
    assert statuses == ["pending", "ready", "ready"]
