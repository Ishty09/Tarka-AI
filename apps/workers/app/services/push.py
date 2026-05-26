"""Push notification rendering + delivery (CLAUDE.md §13, §6.6).

Templates are loaded from `apps/web/messages/{locale}.json` so the strings
stay in one place — the same JSON powers next-intl on the web client and
this service for cron-driven sends. Per CLAUDE.md §8 no hardcoded English
in JSX; the same constraint applies here so push copy stays translatable.

Delivery model:
- Web Push (browser) — requires VAPID-signed JWT auth. The actual signing
  isn't wired here (deferred to deployment when keys + service worker
  exist). A pluggable `WebPushSender` protocol lets us substitute the
  real implementation later without touching call sites.
- Expo Push (iOS/Android via Expo) — straightforward HTTP POST to
  https://exp.host/--/api/v2/push/send; no auth header required for
  development, but production accepts an Expo access token to raise
  rate limits and surface deliveries.

Idempotency: pass `idempotency_key` for any event that can fire twice
(cron retries, webhook deliveries). We dedupe against `idempotency_keys`
with scope=`push:<template>`. Without a key, every call ships — only
appropriate for one-shot user-triggered events.

CLAUDE.md §22: no PII in logs. We log a hash of the token, never the raw
token; we log template+locale, never the rendered body.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx
import structlog
from supabase import AsyncClient

from app.config import get_settings
from app.services._db_typing import row_or_none
from app.services._db_typing import rows as _rows
from app.services.supabase_client import get_supabase

log = structlog.get_logger(__name__)


# ----- Template keys -------------------------------------------------------


PushTemplate = Literal[
    "daily_roast",
    "contradiction",
    "couples_invite",
    "couples_dispute_created",
    "couples_dispute_perspective_added",
    "couples_dispute_arbitrated",
    "couples_report_ready",
    "wager_checkin",
    "wager_failed",
    "mirror_ready",
    "eulogy_ready",
    "streak_punish",
]


PUSH_TEMPLATES: tuple[PushTemplate, ...] = (
    "daily_roast",
    "contradiction",
    "couples_invite",
    "couples_dispute_created",
    "couples_dispute_perspective_added",
    "couples_dispute_arbitrated",
    "couples_report_ready",
    "wager_checkin",
    "wager_failed",
    "mirror_ready",
    "eulogy_ready",
    "streak_punish",
)

DEFAULT_LOCALE = "en"


# ----- Locale loading ------------------------------------------------------


def _messages_root() -> Path:
    # Workers root is apps/workers/. Messages live at apps/web/messages/.
    # Allow override for tests + deploys where the layout differs.
    here = Path(__file__).resolve()
    workers_root = here.parents[2]  # services -> app -> workers
    default = workers_root.parent / "web" / "messages"
    return default


_messages_cache: dict[str, dict[str, str]] | None = None


def _load_all_messages(root: Path | None = None) -> dict[str, dict[str, str]]:
    """Read every {locale}.json into a {locale -> {key -> str}} map."""

    base = root or _messages_root()
    out: dict[str, dict[str, str]] = {}
    if not base.exists():
        return out
    for path in sorted(base.glob("*.json")):
        try:
            locale = path.stem
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                # apps/web/messages now uses nested objects (next-intl
                # expects dot-keys to traverse). Flatten back to flat
                # dot-keys here so existing render_push consumers
                # (`push.daily_roast.title` etc.) work unchanged.
                out[locale] = _flatten_dict(data)
        except (OSError, json.JSONDecodeError) as err:
            log.warning("push.locale_load_failed", path=str(path), error=str(err))
    return out


def _flatten_dict(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in data.items():
        full = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(_flatten_dict(value, prefix=f"{full}."))
        elif isinstance(value, str):
            out[full] = value
    return out


def messages(root: Path | None = None, *, force_reload: bool = False) -> dict[str, dict[str, str]]:
    global _messages_cache
    if _messages_cache is None or force_reload or root is not None:
        loaded = _load_all_messages(root)
        if root is None:
            _messages_cache = loaded
        return loaded
    return _messages_cache


def supported_locales(root: Path | None = None) -> list[str]:
    return sorted(messages(root).keys())


# ----- Render --------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class PushPayload:
    title: str
    body: str
    data: dict[str, Any]


class MissingTemplateError(KeyError):
    """Raised when a locale doesn't carry a needed push.* key."""


def _format(template_str: str, variables: dict[str, Any]) -> str:
    # str.format_map with a missing-key proxy so we surface a precise error
    # rather than KeyError(template).
    try:
        return template_str.format_map(variables)
    except KeyError as err:
        raise MissingTemplateError(
            f"missing variable {err.args[0]} for push template"
        ) from err


def render_push(
    template: PushTemplate,
    *,
    locale: str,
    variables: dict[str, Any],
    deep_link: str | None = None,
    root: Path | None = None,
) -> PushPayload:
    """Render title + body for the (template, locale) pair.

    Falls back to English when a locale doesn't carry the keys yet —
    silent fallback is preferable to dropping a notification, but we
    log it so missing translations surface in metrics.
    """

    all_messages = messages(root)
    title_key = f"push.{template}.title"
    body_key = f"push.{template}.body"

    locale_messages = all_messages.get(locale)
    if (
        locale_messages is None
        or title_key not in locale_messages
        or body_key not in locale_messages
    ):
        fallback = all_messages.get(DEFAULT_LOCALE)
        if fallback is None or title_key not in fallback or body_key not in fallback:
            raise MissingTemplateError(f"{template} missing for both {locale} and {DEFAULT_LOCALE}")
        if locale != DEFAULT_LOCALE:
            log.info(
                "push.locale_fallback",
                template=template,
                requested=locale,
                used=DEFAULT_LOCALE,
            )
        locale_messages = fallback

    title = _format(locale_messages[title_key], variables)
    body = _format(locale_messages[body_key], variables)
    data: dict[str, Any] = {"template": template}
    if deep_link:
        data["url"] = deep_link
    return PushPayload(title=title, body=body, data=data)


# ----- Sender protocols ----------------------------------------------------


@dataclass(slots=True, frozen=True)
class PushSubscriptionRow:
    id: str
    platform: Literal["web", "ios", "android"]
    token: str


@dataclass(slots=True, frozen=True)
class DeliveryResult:
    subscription_id: str
    status: Literal["sent", "skipped", "failed", "dry_run"]
    reason: str | None = None


class WebPushSender(Protocol):
    async def send(
        self,
        *,
        subscription: PushSubscriptionRow,
        payload: PushPayload,
    ) -> DeliveryResult: ...


class ExpoPushSender(Protocol):
    async def send(
        self,
        *,
        subscription: PushSubscriptionRow,
        payload: PushPayload,
    ) -> DeliveryResult: ...


class _DryRunWebPushSender:
    """Default WebPushSender — logs and returns dry_run.

    Real Web Push needs VAPID-signed JWTs (RFC 8292). We wire those in
    when service-worker + VAPID keys are deployed (post-§27 step 70).
    Until then, web push subscriptions are persisted but not delivered;
    the message that would have notified still appears inline in the app.
    """

    async def send(
        self,
        *,
        subscription: PushSubscriptionRow,
        payload: PushPayload,
    ) -> DeliveryResult:
        log.info(
            "push.web.dry_run",
            subscription_hash=_hash_token(subscription.token),
            title=payload.title,
        )
        return DeliveryResult(
            subscription_id=subscription.id,
            status="dry_run",
            reason="vapid_not_configured",
        )


class _HttpExpoPushSender:
    """Production-ready Expo sender. Posts a single notification to
    https://exp.host/--/api/v2/push/send. We don't batch — Expo's API
    accepts a list, but at our volumes per-token POSTs keep retry logic
    simple. EXPO_ACCESS_TOKEN raises the per-hour rate limit when set.
    """

    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def send(
        self,
        *,
        subscription: PushSubscriptionRow,
        payload: PushPayload,
    ) -> DeliveryResult:
        body = {
            "to": subscription.token,
            "title": payload.title,
            "body": payload.body,
            "data": payload.data,
            "priority": "high",
            "sound": "default",
        }
        headers = {"content-type": "application/json"}
        access = get_settings().expo_access_token
        if access:
            headers["authorization"] = f"Bearer {access}"

        own_client = self._client is None
        http = self._client or httpx.AsyncClient(timeout=15.0)
        try:
            resp = await http.post(
                "https://exp.host/--/api/v2/push/send",
                headers=headers,
                json=body,
            )
            if resp.status_code >= 400:
                log.warning(
                    "push.expo.failed",
                    subscription_hash=_hash_token(subscription.token),
                    status=resp.status_code,
                )
                return DeliveryResult(
                    subscription_id=subscription.id,
                    status="failed",
                    reason=f"expo_{resp.status_code}",
                )
            return DeliveryResult(subscription_id=subscription.id, status="sent")
        except httpx.HTTPError as err:
            log.warning(
                "push.expo.network_error",
                subscription_hash=_hash_token(subscription.token),
                error=str(err),
            )
            return DeliveryResult(
                subscription_id=subscription.id, status="failed", reason="network"
            )
        finally:
            if own_client:
                await http.aclose()


def _hash_token(token: str) -> str:
    return hmac.new(
        b"push-token-hash",
        token.encode(),
        hashlib.sha256,
    ).hexdigest()[:16]


# ----- Orchestration -------------------------------------------------------


async def _load_subscriptions(
    supabase: AsyncClient, *, user_id: str
) -> list[PushSubscriptionRow]:
    res = (
        await supabase.table("push_subscriptions")
        .select("id, platform, token")
        .eq("user_id", user_id)
        .execute()
    )
    out: list[PushSubscriptionRow] = []
    for row in _rows(res.data):
        platform = row.get("platform")
        token = row.get("token")
        sub_id = row.get("id")
        if not isinstance(platform, str) or platform not in ("web", "ios", "android"):
            continue
        if not isinstance(token, str) or not token:
            continue
        if not isinstance(sub_id, str):
            continue
        out.append(PushSubscriptionRow(id=sub_id, platform=platform, token=token))  # type: ignore[arg-type]
    return out


async def _load_locale(supabase: AsyncClient, *, user_id: str) -> str:
    res = (
        await supabase.table("profiles")
        .select("locale, notification_push")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    row = row_or_none(res.data) if res is not None else None
    if row is None:
        return DEFAULT_LOCALE
    if row.get("notification_push") is False:
        return ""  # caller treats empty as "muted"
    locale = row.get("locale")
    return locale if isinstance(locale, str) and locale else DEFAULT_LOCALE


async def _idempotency_seen(supabase: AsyncClient, *, key: str) -> bool:
    res = (
        await supabase.table("idempotency_keys")
        .select("key")
        .eq("key", key)
        .maybe_single()
        .execute()
    )
    return row_or_none(res.data) is not None if res is not None else False


async def _idempotency_record(
    supabase: AsyncClient,
    *,
    key: str,
    template: PushTemplate,
    user_id: str,
) -> None:
    await (
        supabase.table("idempotency_keys")
        .insert(
            {
                "key": key,
                "scope": f"push:{template}",
                "user_id": user_id,
                "payload_hash": "",
                "response_status": 0,
                "response_body": None,
                "expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
            }
        )
        .execute()
    )


async def deliver_to_user(
    *,
    user_id: str,
    template: PushTemplate,
    variables: dict[str, Any],
    deep_link: str | None = None,
    idempotency_key: str | None = None,
    supabase: AsyncClient | None = None,
    web_sender: WebPushSender | None = None,
    expo_sender: ExpoPushSender | None = None,
) -> list[DeliveryResult]:
    """Render once for the user's locale, dispatch to every active sub.

    Returns one DeliveryResult per subscription. If the user has muted
    push notifications, returns an empty list (no rows recorded).
    """

    sb = supabase or await get_supabase()

    if idempotency_key is not None and await _idempotency_seen(sb, key=idempotency_key):
        log.info(
            "push.idempotent_skip",
            user_id=user_id,
            template=template,
            key=idempotency_key,
        )
        return []

    locale = await _load_locale(sb, user_id=user_id)
    if locale == "":
        log.info("push.muted", user_id=user_id, template=template)
        return []

    subscriptions = await _load_subscriptions(sb, user_id=user_id)
    if not subscriptions:
        return []

    payload = render_push(
        template,
        locale=locale,
        variables=variables,
        deep_link=deep_link,
    )

    web = web_sender or _DryRunWebPushSender()
    expo = expo_sender or _HttpExpoPushSender()

    results: list[DeliveryResult] = []
    for sub in subscriptions:
        if sub.platform == "web":
            res = await web.send(subscription=sub, payload=payload)
        else:
            res = await expo.send(subscription=sub, payload=payload)
        results.append(res)

    if idempotency_key is not None:
        await _idempotency_record(
            sb,
            key=idempotency_key,
            template=template,
            user_id=user_id,
        )

    return results


__all__ = [
    "DEFAULT_LOCALE",
    "PUSH_TEMPLATES",
    "DeliveryResult",
    "ExpoPushSender",
    "MissingTemplateError",
    "PushPayload",
    "PushSubscriptionRow",
    "PushTemplate",
    "WebPushSender",
    "deliver_to_user",
    "messages",
    "render_push",
    "supported_locales",
]
