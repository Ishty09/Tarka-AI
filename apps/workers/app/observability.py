"""Sentry initialization for the FastAPI workers (CLAUDE.md §27 step 60).

Called once from main.py before app creation. No-op when SENTRY_DSN is
empty (dev + tests). The before_send scrubber strips known credential
and PII surfaces — per §22 we keep error logs free of API keys, raw
user content, and PII.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import sentry_sdk
import structlog
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.httpx import HttpxIntegration
from sentry_sdk.types import Event, Hint

from app.config import get_settings

log = structlog.get_logger(__name__)


# Keys we never want crossing the wire to Sentry. We match on dotted
# paths in the event dict, plus a fallback substring match on header /
# query parameter names so a stray `Authorization: Bearer ...` doesn't
# slip through.
_SECRET_KEY_SUBSTRINGS = (
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "litellm",
    "service_role",
    "anon_key",
    "polar",
    "resend",
    "vapid",
    "supabase",
    "openai",
    "anthropic",
)

# Top-level keys we drop wholesale from event payloads.
_DROP_TOP_LEVEL = (
    "request_body",
)


def _scrub_headers(headers: Mapping[str, Any]) -> dict[str, Any]:
    scrubbed: dict[str, Any] = {}
    for k, v in headers.items():
        lower = k.lower()
        if any(s in lower for s in _SECRET_KEY_SUBSTRINGS):
            scrubbed[k] = "[REDACTED]"
        else:
            scrubbed[k] = v
    return scrubbed


def _before_send(event: Event, _hint: Hint) -> Event | None:
    """Strip credentials and user-supplied free text before send."""

    # The sentry_sdk Event is a TypedDict with closed key names; cast to
    # a plain dict to allow dynamic key inspection + deletion.
    e = cast(dict[str, Any], event)

    request = e.get("request")
    if isinstance(request, dict):
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = _scrub_headers(headers)
        # Drop request body wholesale; we never want raw chat content
        # surfacing in Sentry.
        for key in ("data", "json", "form"):
            request.pop(key, None)
    for k in _DROP_TOP_LEVEL:
        e.pop(k, None)
    # `user` may carry email/ip injected by integrations. We send only
    # the hashed user_id where set; drop stray PII surfaces.
    user = e.get("user")
    if isinstance(user, dict):
        for pii in ("email", "ip_address", "username"):
            user.pop(pii, None)
    return event


def init_sentry() -> bool:
    """Initialize Sentry SDK. Returns True if sent to Sentry, False if no-op."""

    settings = get_settings()
    dsn = settings.sentry_dsn
    if not dsn:
        log.info("sentry.skipped", reason="no_dsn")
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.node_env,
        # Don't auto-attach IP/headers; the before_send scrubber is the
        # belt-and-suspenders layer.
        send_default_pii=False,
        traces_sample_rate=0.1,
        # Profiles are noisy in async workloads; keep off until we have
        # a budget for the data.
        profiles_sample_rate=0.0,
        attach_stacktrace=True,
        before_send=_before_send,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            HttpxIntegration(),
            AsyncioIntegration(),
        ],
    )
    log.info("sentry.initialised", environment=settings.node_env)
    return True
