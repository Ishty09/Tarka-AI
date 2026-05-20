"""Polar webhook processing (CLAUDE.md §3, §8, §22, §1.11).

Polar uses the StandardWebhooks signing scheme. Per request the payload to
verify is `{webhook-id}.{webhook-timestamp}.{raw-body}`; the signature
header carries one or more `v1,<base64-sha256>` tokens that we
constant-time compare against an HMAC-SHA256 of that payload with the
webhook secret. We accept the request if ANY of those tokens matches —
Polar rotates the signing key occasionally and sends both.

Idempotency: every webhook body carries an `id` (the event id) AND the
top-level `webhook-id` header. We use the header — it's the canonical
delivery id — as the key in `idempotency_keys`. A retry of the same
event is a no-op (200 status, payload "skipped").

Event handlers update `subscriptions` (one row per Polar subscription)
AND `profiles.tier` (denormalized for fast read). Both writes happen
under the worker's service-role client so the §6.7 admin-only policies
don't get in the way; the webhook is itself the trust boundary.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import structlog
from supabase import AsyncClient

from app.config import get_settings
from app.services._db_typing import row_or_none

log = structlog.get_logger(__name__)


# StandardWebhooks: max age before we reject the timestamp as replayed.
MAX_TIMESTAMP_SKEW = timedelta(minutes=5)


# ----- Signature verification --------------------------------------------


class InvalidSignatureError(Exception):
    """Raised when the webhook's signature header doesn't validate."""


def _decode_secret(raw: str) -> bytes:
    """Polar webhook secrets are prefixed with `whsec_` and base64-encoded."""

    body = raw.removeprefix("whsec_") if raw.startswith("whsec_") else raw
    try:
        return base64.b64decode(body)
    except (ValueError, base64.binascii.Error):  # type: ignore[attr-defined]
        # Treat malformed secret as a configuration bug — fail loudly.
        raise InvalidSignatureError("secret_unparseable")


def verify_signature(
    *,
    body: bytes,
    webhook_id: str,
    webhook_timestamp: str,
    signature_header: str,
    secret: str | None = None,
    now: datetime | None = None,
) -> None:
    """Raises InvalidSignatureError if the request can't be trusted."""

    settings = get_settings()
    resolved_secret = secret if secret is not None else settings.polar_webhook_secret
    if not resolved_secret:
        raise InvalidSignatureError("secret_unset")

    if not webhook_id or not webhook_timestamp or not signature_header:
        raise InvalidSignatureError("headers_missing")

    try:
        ts_epoch = int(webhook_timestamp)
    except (TypeError, ValueError) as err:
        raise InvalidSignatureError("timestamp_unparseable") from err

    current = now or datetime.now(UTC)
    delta = abs(current - datetime.fromtimestamp(ts_epoch, tz=UTC))
    if delta > MAX_TIMESTAMP_SKEW:
        raise InvalidSignatureError("timestamp_skew")

    key = _decode_secret(resolved_secret)
    signed = f"{webhook_id}.{webhook_timestamp}.".encode() + body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()

    # Header may be a space-separated list of `v1,<sig>` tokens.
    tokens = signature_header.split()
    if not tokens:
        raise InvalidSignatureError("signature_empty")

    for token in tokens:
        version, _, sig = token.partition(",")
        if version != "v1" or not sig:
            continue
        if hmac.compare_digest(sig, expected):
            return
    raise InvalidSignatureError("signature_mismatch")


# ----- Idempotency -------------------------------------------------------


async def is_seen(supabase: AsyncClient, *, event_id: str) -> bool:
    res = (
        await supabase.table("idempotency_keys")
        .select("key")
        .eq("key", _idempotency_key(event_id))
        .maybe_single()
        .execute()
    )
    return row_or_none(res.data) is not None if res is not None else False


async def mark_seen(
    supabase: AsyncClient,
    *,
    event_id: str,
    event_type: str,
    response_status: int = 200,
) -> None:
    await (
        supabase.table("idempotency_keys")
        .insert(
            {
                "key": _idempotency_key(event_id),
                "scope": f"polar_webhook:{event_type}",
                "user_id": None,
                "payload_hash": "",
                "response_status": response_status,
                "response_body": None,
                "expires_at": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
            }
        )
        .execute()
    )


def _idempotency_key(event_id: str) -> str:
    return f"polar:{event_id}"


# ----- Event shape -------------------------------------------------------


@dataclass(slots=True, frozen=True)
class PolarEvent:
    type: str
    data: dict[str, Any]
    raw: dict[str, Any]


def parse_event(body: bytes) -> PolarEvent:
    parsed = json.loads(body.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("polar_event_not_object")
    event_type = parsed.get("type")
    data = parsed.get("data")
    if not isinstance(event_type, str) or not isinstance(data, dict):
        raise ValueError("polar_event_missing_fields")
    return PolarEvent(type=event_type, data=data, raw=parsed)


# ----- Subscription handlers ---------------------------------------------


# Map Polar product IDs to (tier, interval). Resolved at handle-time so
# changing env doesn't require a restart.
def _product_to_tier(product_id: str) -> tuple[Literal["pro", "max"] | None, str | None]:
    settings = get_settings()
    table: dict[str, tuple[Literal["pro", "max"], str]] = {
        settings.polar_product_id_pro_monthly: ("pro", "monthly"),
        settings.polar_product_id_pro_annual: ("pro", "annual"),
        settings.polar_product_id_max_monthly: ("max", "monthly"),
        settings.polar_product_id_max_annual: ("max", "annual"),
    }
    table.pop("", None)
    if product_id in table:
        return table[product_id]
    return None, None


def _extract_user_id(data: dict[str, Any]) -> str | None:
    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        candidate = metadata.get("user_id")
        if isinstance(candidate, str) and candidate:
            return candidate
    # Some Polar payloads also store our linkage under customer_email/customer_id;
    # neither maps to our auth.users.id, so metadata is the only reliable
    # source. Caller logs + skips when we can't resolve a user.
    return None


def _resolve_tier(data: dict[str, Any]) -> Literal["pro", "max"] | None:
    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        m_tier = metadata.get("tier")
        if m_tier == "pro":
            return "pro"
        if m_tier == "max":
            return "max"

    product_id = data.get("product_id")
    if isinstance(product_id, str):
        tier, _ = _product_to_tier(product_id)
        if tier:
            return tier
    return None


@dataclass(slots=True, frozen=True)
class HandlerOutcome:
    status: Literal["applied", "ignored", "skipped"]
    reason: str | None = None


async def _upsert_subscription(
    supabase: AsyncClient,
    *,
    user_id: str,
    tier: Literal["pro", "max"],
    data: dict[str, Any],
    derived_status: str,
) -> None:
    payload: dict[str, Any] = {
        "user_id": user_id,
        "tier": tier,
        "status": derived_status,
        "source": "polar",
        "external_subscription_id": str(data.get("id")),
        "current_period_start": data.get("current_period_start"),
        "current_period_end": data.get("current_period_end"),
        "cancel_at_period_end": bool(data.get("cancel_at_period_end", False)),
        "canceled_at": data.get("canceled_at"),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    await (
        supabase.table("subscriptions")
        .upsert(payload, on_conflict="source,external_subscription_id")
        .execute()
    )


async def _sync_profile_tier(
    supabase: AsyncClient,
    *,
    user_id: str,
    tier: Literal["free", "pro", "max"],
) -> None:
    await (
        supabase.table("profiles")
        .update(
            {
                "tier": tier,
                "tier_source": "polar" if tier != "free" else None,
            }
        )
        .eq("id", user_id)
        .execute()
    )


_ACTIVATING = {"subscription.created", "subscription.active", "subscription.updated"}
_CANCELING = {"subscription.canceled"}
_REVOKING = {"subscription.revoked"}
_RESTORING = {"subscription.uncanceled"}


async def handle_event(
    supabase: AsyncClient,
    event: PolarEvent,
) -> HandlerOutcome:
    """Dispatch a parsed Polar event. Returns 'ignored' for events we don't act on."""

    if (
        event.type not in _ACTIVATING
        and event.type not in _CANCELING
        and event.type not in _REVOKING
        and event.type not in _RESTORING
    ):
        return HandlerOutcome(status="ignored", reason="unhandled_event_type")

    user_id = _extract_user_id(event.data)
    if user_id is None:
        log.warning("polar.webhook.missing_user", event_type=event.type)
        return HandlerOutcome(status="ignored", reason="missing_user_metadata")

    tier = _resolve_tier(event.data)
    if tier is None:
        log.warning(
            "polar.webhook.tier_unresolved",
            event_type=event.type,
            product_id=event.data.get("product_id"),
        )
        return HandlerOutcome(status="ignored", reason="tier_unresolved")

    status_field = event.data.get("status")
    derived_status = _derive_subscription_status(
        event_type=event.type,
        polar_status=status_field if isinstance(status_field, str) else None,
    )

    await _upsert_subscription(
        supabase,
        user_id=user_id,
        tier=tier,
        data=event.data,
        derived_status=derived_status,
    )

    # Profile sync: revoke → drop to free; everything else keeps the paid tier.
    if event.type in _REVOKING:
        await _sync_profile_tier(supabase, user_id=user_id, tier="free")
    else:
        await _sync_profile_tier(supabase, user_id=user_id, tier=tier)

    return HandlerOutcome(status="applied")


def _derive_subscription_status(
    *,
    event_type: str,
    polar_status: str | None,
) -> str:
    """Map Polar's status + event into our `subscriptions.status` CHECK domain."""

    valid = {"active", "past_due", "canceled", "paused", "trialing"}
    if event_type in _REVOKING:
        return "canceled"
    if event_type in _CANCELING:
        # Polar marks cancel_at_period_end=true but subscription is still active
        # through the current period — keep status 'active'.
        if polar_status in valid:
            return polar_status
        return "active"
    if polar_status in valid:
        return polar_status
    return "active"


__all__ = [
    "HandlerOutcome",
    "InvalidSignatureError",
    "PolarEvent",
    "handle_event",
    "is_seen",
    "mark_seen",
    "parse_event",
    "verify_signature",
]
