"""Polar webhook: signature, idempotency, subscription state machine."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
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

from app.services import polar_webhooks as pw
from app.services.polar_webhooks import (
    InvalidSignatureError,
    handle_event,
    is_seen,
    mark_seen,
    parse_event,
    verify_signature,
)

# ----- Fake supabase --------------------------------------------------------


class _Res:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Q:
    def __init__(self, table: _Table, op: str, payload: Any = None) -> None:
        self._t = table
        self._op = op
        self._payload = payload
        self._filters: list[tuple[str, Any]] = []
        self._maybe_single = False
        self._on_conflict: str | None = None

    def select(self, _cols: str = "*") -> _Q:
        return self

    def eq(self, col: str, val: Any) -> _Q:
        self._filters.append((col, val))
        return self

    def maybe_single(self) -> _Q:
        self._maybe_single = True
        return self

    async def execute(self) -> _Res:
        if self._op == "select":
            rows = [r for r in self._t.rows if all(r.get(c) == v for c, v in self._filters)]
            if self._maybe_single:
                return _Res(rows[0] if rows else None)
            return _Res(rows)

        if self._op == "insert":
            payloads = self._payload if isinstance(self._payload, list) else [self._payload]
            for p in payloads:
                self._t.rows.append(dict(p))
            return _Res(payloads)

        if self._op == "update":
            for r in self._t.rows:
                if all(r.get(c) == v for c, v in self._filters):
                    r.update(self._payload)
            return _Res(None)

        if self._op == "upsert":
            payloads = self._payload if isinstance(self._payload, list) else [self._payload]
            key_cols = self._on_conflict.split(",") if self._on_conflict else ["id"]
            for p in payloads:
                match = None
                for r in self._t.rows:
                    if all(r.get(c) == p.get(c) for c in key_cols):
                        match = r
                        break
                if match is not None:
                    match.update(p)
                else:
                    self._t.rows.append(dict(p))
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

    def upsert(self, payload: Any, *, on_conflict: str | None = None) -> _Q:
        q = _Q(self, "upsert", payload)
        q._on_conflict = on_conflict
        return q


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, _Table] = {}

    def table(self, name: str) -> _Table:
        self.tables.setdefault(name, _Table(name))
        return self.tables[name]


# ----- Signature helpers ---------------------------------------------------


SECRET_B64 = base64.b64encode(b"verysecretkey").decode()
SECRET = f"whsec_{SECRET_B64}"


def _sign(body: bytes, webhook_id: str, ts: str) -> str:
    payload = f"{webhook_id}.{ts}.".encode() + body
    sig = base64.b64encode(
        hmac.new(b"verysecretkey", payload, hashlib.sha256).digest()
    ).decode()
    return f"v1,{sig}"


# ----- Tests: signature ----------------------------------------------------


def test_verify_signature_accepts_valid() -> None:
    body = b'{"hello":"world"}'
    ts = str(int(datetime.now(UTC).timestamp()))
    wid = "evt_1"
    header = _sign(body, wid, ts)
    # Should not raise.
    verify_signature(
        body=body,
        webhook_id=wid,
        webhook_timestamp=ts,
        signature_header=header,
        secret=SECRET,
    )


def test_verify_signature_rejects_tampered_body() -> None:
    body = b'{"hello":"world"}'
    ts = str(int(datetime.now(UTC).timestamp()))
    wid = "evt_1"
    header = _sign(body, wid, ts)
    with pytest.raises(InvalidSignatureError):
        verify_signature(
            body=b'{"hello":"world!"}',
            webhook_id=wid,
            webhook_timestamp=ts,
            signature_header=header,
            secret=SECRET,
        )


def test_verify_signature_rejects_old_timestamp() -> None:
    body = b"{}"
    old = datetime.now(UTC) - timedelta(minutes=10)
    ts = str(int(old.timestamp()))
    wid = "evt_1"
    header = _sign(body, wid, ts)
    with pytest.raises(InvalidSignatureError):
        verify_signature(
            body=body,
            webhook_id=wid,
            webhook_timestamp=ts,
            signature_header=header,
            secret=SECRET,
        )


def test_verify_signature_rejects_missing_secret() -> None:
    with pytest.raises(InvalidSignatureError):
        verify_signature(
            body=b"{}",
            webhook_id="evt_1",
            webhook_timestamp=str(int(datetime.now(UTC).timestamp())),
            signature_header="v1,xxx",
            secret="",
        )


def test_verify_signature_accepts_among_multiple_tokens() -> None:
    body = b"{}"
    ts = str(int(datetime.now(UTC).timestamp()))
    wid = "evt_2"
    good = _sign(body, wid, ts)
    header = f"v1,malformed {good}"
    verify_signature(
        body=body,
        webhook_id=wid,
        webhook_timestamp=ts,
        signature_header=header,
        secret=SECRET,
    )


# ----- Tests: idempotency --------------------------------------------------


@pytest.mark.asyncio
async def test_is_seen_returns_false_initially() -> None:
    sb = FakeSupabase()
    assert await is_seen(sb, event_id="evt_x") is False  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_mark_seen_then_is_seen() -> None:
    sb = FakeSupabase()
    await mark_seen(sb, event_id="evt_x", event_type="subscription.created")  # type: ignore[arg-type]
    assert await is_seen(sb, event_id="evt_x") is True  # type: ignore[arg-type]
    assert sb.tables["idempotency_keys"].rows[0]["scope"] == "polar_webhook:subscription.created"


# ----- Tests: event parsing -----------------------------------------------


def test_parse_event_extracts_type_and_data() -> None:
    body = json.dumps(
        {
            "type": "subscription.created",
            "data": {"id": "sub_x", "status": "active"},
        }
    ).encode()
    out = parse_event(body)
    assert out.type == "subscription.created"
    assert out.data["id"] == "sub_x"


def test_parse_event_rejects_missing_type() -> None:
    body = json.dumps({"data": {}}).encode()
    with pytest.raises(ValueError, match="polar_event_missing_fields"):
        parse_event(body)


# ----- Tests: handler ------------------------------------------------------


@pytest.fixture(autouse=True)
def _set_product_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import Settings

    fake = Settings(
        NEXT_PUBLIC_APP_URL="https://quarrel.test",
        LITELLM_PROXY_URL="https://litellm.test",
        LITELLM_MASTER_KEY="x",
        NEXT_PUBLIC_SUPABASE_URL="https://supabase.test",
        SUPABASE_SERVICE_ROLE_KEY="x",
        NEXT_PUBLIC_SUPABASE_ANON_KEY="x",
        POLAR_PRODUCT_ID_PRO_MONTHLY="prod_pro_m",
        POLAR_PRODUCT_ID_PRO_ANNUAL="prod_pro_a",
        POLAR_PRODUCT_ID_MAX_MONTHLY="prod_max_m",
        POLAR_PRODUCT_ID_MAX_ANNUAL="prod_max_a",
        POLAR_WEBHOOK_SECRET=SECRET,
    )
    monkeypatch.setattr(pw, "get_settings", lambda: fake)


def _make_event(event_type: str, **data: Any) -> Any:
    base = {
        "id": "sub_abc",
        "status": "active",
        "product_id": "prod_pro_m",
        "current_period_start": "2026-05-19T00:00:00Z",
        "current_period_end": "2026-06-19T00:00:00Z",
        "cancel_at_period_end": False,
        "canceled_at": None,
        "metadata": {"user_id": "u1", "tier": "pro", "interval": "monthly"},
        **data,
    }
    return parse_event(json.dumps({"type": event_type, "data": base}).encode())


@pytest.mark.asyncio
async def test_subscription_created_writes_subscription_and_profile() -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.append({"id": "u1", "tier": "free", "tier_source": None})

    outcome = await handle_event(sb, _make_event("subscription.created"))  # type: ignore[arg-type]
    assert outcome.status == "applied"

    subs = sb.tables["subscriptions"].rows
    assert len(subs) == 1
    assert subs[0]["tier"] == "pro"
    assert subs[0]["status"] == "active"
    assert subs[0]["source"] == "polar"

    profile = sb.tables["profiles"].rows[0]
    assert profile["tier"] == "pro"
    assert profile["tier_source"] == "polar"


@pytest.mark.asyncio
async def test_subscription_updated_upserts_same_row() -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.append({"id": "u1", "tier": "free"})

    await handle_event(sb, _make_event("subscription.created"))  # type: ignore[arg-type]
    await handle_event(
        sb,
        _make_event("subscription.updated", cancel_at_period_end=True),  # type: ignore[arg-type]
    )
    subs = sb.tables["subscriptions"].rows
    assert len(subs) == 1
    assert subs[0]["cancel_at_period_end"] is True


@pytest.mark.asyncio
async def test_subscription_canceled_keeps_tier_until_period_end() -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.append({"id": "u1", "tier": "pro", "tier_source": "polar"})

    await handle_event(
        sb,
        _make_event(
            "subscription.canceled",
            cancel_at_period_end=True,
            canceled_at="2026-05-20T00:00:00Z",
        ),  # type: ignore[arg-type]
    )

    profile = sb.tables["profiles"].rows[0]
    # User still has pro until period_end — billing-side cancellation.
    assert profile["tier"] == "pro"
    assert sb.tables["subscriptions"].rows[0]["cancel_at_period_end"] is True
    assert sb.tables["subscriptions"].rows[0]["canceled_at"] == "2026-05-20T00:00:00Z"


@pytest.mark.asyncio
async def test_subscription_revoked_drops_tier_to_free() -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.append({"id": "u1", "tier": "pro", "tier_source": "polar"})

    await handle_event(sb, _make_event("subscription.revoked"))  # type: ignore[arg-type]

    profile = sb.tables["profiles"].rows[0]
    assert profile["tier"] == "free"
    assert profile["tier_source"] is None
    assert sb.tables["subscriptions"].rows[0]["status"] == "canceled"


@pytest.mark.asyncio
async def test_unhandled_event_type_returns_ignored() -> None:
    sb = FakeSupabase()
    outcome = await handle_event(
        sb,
        parse_event(json.dumps({"type": "order.refunded", "data": {}}).encode()),  # type: ignore[arg-type]
    )
    assert outcome.status == "ignored"


@pytest.mark.asyncio
async def test_missing_user_metadata_is_ignored() -> None:
    sb = FakeSupabase()
    event = parse_event(
        json.dumps(
            {
                "type": "subscription.created",
                "data": {
                    "id": "sub_x",
                    "status": "active",
                    "product_id": "prod_pro_m",
                    "metadata": {},
                },
            }
        ).encode()
    )
    outcome = await handle_event(sb, event)  # type: ignore[arg-type]
    assert outcome.status == "ignored"
    assert outcome.reason == "missing_user_metadata"


@pytest.mark.asyncio
async def test_resolves_tier_from_product_when_metadata_missing() -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.append({"id": "u1", "tier": "free"})
    event = parse_event(
        json.dumps(
            {
                "type": "subscription.active",
                "data": {
                    "id": "sub_y",
                    "status": "active",
                    "product_id": "prod_max_a",
                    "current_period_start": "2026-05-19T00:00:00Z",
                    "current_period_end": "2027-05-19T00:00:00Z",
                    "cancel_at_period_end": False,
                    "canceled_at": None,
                    "metadata": {"user_id": "u1"},
                },
            }
        ).encode()
    )
    outcome = await handle_event(sb, event)  # type: ignore[arg-type]
    assert outcome.status == "applied"
    assert sb.tables["subscriptions"].rows[0]["tier"] == "max"


@pytest.mark.asyncio
async def test_uncanceled_clears_cancel_at_period_end() -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.append({"id": "u1", "tier": "pro", "tier_source": "polar"})

    await handle_event(
        sb,
        _make_event(
            "subscription.canceled",
            cancel_at_period_end=True,
            canceled_at="2026-05-20T00:00:00Z",
        ),  # type: ignore[arg-type]
    )
    await handle_event(
        sb,
        _make_event(
            "subscription.uncanceled",
            cancel_at_period_end=False,
            canceled_at=None,
        ),  # type: ignore[arg-type]
    )
    sub = sb.tables["subscriptions"].rows[0]
    assert sub["cancel_at_period_end"] is False
    assert sub["canceled_at"] is None
