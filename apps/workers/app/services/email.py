"""Transactional + lifecycle email (CLAUDE.md §14).

All 14 templates live here as Jinja2 string templates (HTML + plaintext)
keyed by name. `send_email(template=...)` renders + ships via Resend's
HTTP API; idempotency is enforced through the `idempotency_keys` table
when the caller supplies a key (recommended for everything driven by
webhooks or cron — §1.11).

Design choices:
- One file. Easier to scan all copy in one place than chase 14 files.
- Template strings, not files on disk. Lets tests assert on rendered
  output without filesystem fixtures.
- Plaintext + HTML rendered from separate templates. We could derive
  plaintext from HTML but the wording wants to differ slightly (HTML
  has links, plaintext spells out URLs).
- Idempotency is opt-in via `idempotency_key`. Cron callers should set
  one matching the event (e.g. `email:wager_won:<wager_id>`); ad-hoc
  flows (welcome triggered by a single signup) can omit it.
- Dev mode: when RESEND_API_KEY is empty, we log + skip the HTTP call.
  This keeps tests and local dev from hitting the network.

CLAUDE.md §22: never log raw PII. We log template + a HASH of `to`,
never the raw email address. The email body itself is never logged.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx
import structlog
from jinja2 import Environment, StrictUndefined
from supabase import AsyncClient

from app.config import get_settings
from app.services._db_typing import row_or_none
from app.services.supabase_client import get_supabase

log = structlog.get_logger(__name__)


# ----- Template registry ----------------------------------------------------


TemplateName = Literal[
    "welcome",
    "magic_link",
    "subscription_confirmed",
    "subscription_canceled",
    "payment_failed",
    "wager_won",
    "wager_lost",
    "couples_invite",
    "couples_dispute_created",
    "data_export_ready",
    "account_deletion_grace_started",
    "emergency_contact_notification",
    "mirror_report_ready",
    "eulogy_ready",
    "moderation_rejection",
    "beta_invite",
]


@dataclass(frozen=True, slots=True)
class Template:
    name: TemplateName
    subject: str
    html: str
    text: str
    # Transactional templates (account, billing, safety) skip the
    # unsubscribe footer per CAN-SPAM/GDPR carve-outs; everything else
    # MUST include it.
    transactional: bool
    # Required Jinja vars. Used by tests + at render time so a missing
    # key fails loudly instead of producing a half-rendered email.
    required_vars: tuple[str, ...]


# Footer fragments — inserted depending on `transactional`.
_FOOTER_HTML_TRANSACTIONAL = (
    "<hr style='border:none;border-top:1px solid #e5e7eb;margin:32px 0' />"
    "<p style='color:#6b7280;font-size:12px'>"
    "You're getting this because it relates to your Quarrel account. "
    "Questions? <a href='mailto:{support_email}'>{support_email}</a>"
    "<br />{legal_address}"
    "</p>"
)
_FOOTER_TEXT_TRANSACTIONAL = (
    "\n---\n"
    "You're getting this because it relates to your Quarrel account. "
    "Questions? {support_email}\n"
    "{legal_address}\n"
)
_FOOTER_HTML_MARKETING = (
    "<hr style='border:none;border-top:1px solid #e5e7eb;margin:32px 0' />"
    "<p style='color:#6b7280;font-size:12px'>"
    "You're getting this because you opted in. "
    "<a href='{unsubscribe_url}'>Unsubscribe</a> · "
    "<a href='mailto:{support_email}'>{support_email}</a>"
    "<br />{legal_address}"
    "</p>"
)
_FOOTER_TEXT_MARKETING = (
    "\n---\n"
    "You're getting this because you opted in. Unsubscribe: {unsubscribe_url}\n"
    "Support: {support_email}\n"
    "{legal_address}\n"
)


def _wrap(html_body: str) -> str:
    return (
        "<!doctype html><html><body style='font-family:system-ui,sans-serif;"
        "background:#0a0a0a;color:#fafafa;padding:24px'>"
        "<div style='max-width:560px;margin:0 auto;background:#111;border:1px solid #262626;"
        "border-radius:12px;padding:32px'>"
        f"{html_body}"
        "</div></body></html>"
    )


# Every template body is a Jinja2 source string. We render with strict
# undefined to catch missing keys.
TEMPLATES: dict[TemplateName, Template] = {
    "welcome": Template(
        name="welcome",
        subject="Welcome to Quarrel. Let's not be polite.",
        html=_wrap(
            "<h1 style='margin-top:0'>Welcome, {{ display_name }}.</h1>"
            "<p>You signed up for the AI that won't lie to you. Most chatbots are "
            "built to validate you. Quarrel isn't. It will argue, push back, "
            "remember what you said two weeks ago, and quote it at you when you "
            "contradict yourself.</p>"
            "<p>Three good starting moves:</p>"
            "<ul>"
            "<li><a href='{{ app_url }}/chat'>Argue with a Devil's Advocate</a></li>"
            "<li><a href='{{ app_url }}/tools/decision-killer'>"
            "Run a decision through Decision Killer</a></li>"
            "<li><a href='{{ app_url }}/tools/council'>Convene the 5-member Council</a></li>"
            "</ul>"
            "<p>If you ever need a yes-man, you know where to find one.</p>"
        ),
        text=(
            "Welcome, {{ display_name }}.\n\n"
            "You signed up for the AI that won't lie to you. Most chatbots are "
            "built to validate you. Quarrel isn't.\n\n"
            "Try it:\n"
            "- {{ app_url }}/chat\n"
            "- {{ app_url }}/tools/decision-killer\n"
            "- {{ app_url }}/tools/council\n"
        ),
        transactional=True,
        required_vars=("display_name", "app_url"),
    ),
    "magic_link": Template(
        name="magic_link",
        subject="Your sign-in link",
        html=_wrap(
            "<h1 style='margin-top:0'>Sign in to Quarrel</h1>"
            "<p>Click the button to finish signing in. Expires in {{ ttl_minutes }} minutes.</p>"
            "<p><a href='{{ magic_link }}' style='display:inline-block;background:#fafafa;"
            "color:#0a0a0a;padding:12px 24px;border-radius:8px;text-decoration:none;"
            "font-weight:500'>Sign in</a></p>"
            "<p style='color:#9ca3af;font-size:12px'>If you didn't ask for this, ignore it.</p>"
        ),
        text=(
            "Sign in to Quarrel:\n{{ magic_link }}\n\n"
            "Expires in {{ ttl_minutes }} minutes. If you didn't ask for this, ignore it.\n"
        ),
        transactional=True,
        required_vars=("magic_link", "ttl_minutes"),
    ),
    "subscription_confirmed": Template(
        name="subscription_confirmed",
        subject="You're on Quarrel {{ tier|upper }}",
        html=_wrap(
            "<h1 style='margin-top:0'>You're on {{ tier|upper }}.</h1>"
            "<p>Your subscription is active through "
            "<strong>{{ current_period_end }}</strong>.</p>"
            "<p>{{ amount_formatted }} per {{ interval }}. Receipt + invoice history live "
            "in <a href='{{ app_url }}/settings/billing'>Settings → Billing</a>.</p>"
        ),
        text=(
            "You're on {{ tier|upper }}.\n\n"
            "Active through {{ current_period_end }}. {{ amount_formatted }} per {{ interval }}.\n"
            "Billing: {{ app_url }}/settings/billing\n"
        ),
        transactional=True,
        required_vars=(
            "tier",
            "current_period_end",
            "amount_formatted",
            "interval",
            "app_url",
        ),
    ),
    "subscription_canceled": Template(
        name="subscription_canceled",
        subject="Your Quarrel subscription is canceled",
        html=_wrap(
            "<h1 style='margin-top:0'>Subscription canceled.</h1>"
            "<p>You'll keep <strong>{{ tier|upper }}</strong> access until "
            "<strong>{{ access_until }}</strong>. After that, your account moves "
            "back to Free.</p>"
            "<p>If this was a misclick, <a href='{{ app_url }}/settings/billing'>"
            "resubscribe in one tap</a>.</p>"
        ),
        text=(
            "Subscription canceled.\n\n"
            "You'll keep {{ tier|upper }} access until {{ access_until }}.\n"
            "Resubscribe: {{ app_url }}/settings/billing\n"
        ),
        transactional=True,
        required_vars=("tier", "access_until", "app_url"),
    ),
    "payment_failed": Template(
        name="payment_failed",
        subject="Quarrel: your payment didn't go through",
        html=_wrap(
            "<h1 style='margin-top:0'>Payment failed.</h1>"
            "<p>We couldn't charge your card for <strong>{{ amount_formatted }}</strong>. "
            "Your {{ tier|upper }} access continues until "
            "<strong>{{ grace_until }}</strong> — after that it drops to Free until "
            "billing is fixed.</p>"
            "<p><a href='{{ manage_url }}'>Update your payment method →</a></p>"
        ),
        text=(
            "Payment failed.\n\n"
            "Couldn't charge your card for {{ amount_formatted }}. "
            "{{ tier|upper }} access continues until {{ grace_until }}.\n"
            "Update payment: {{ manage_url }}\n"
        ),
        transactional=True,
        required_vars=("amount_formatted", "tier", "grace_until", "manage_url"),
    ),
    "wager_won": Template(
        name="wager_won",
        subject="You won. {{ stake_formatted }} is yours.",
        html=_wrap(
            "<h1 style='margin-top:0'>You won.</h1>"
            "<p>Goal: <em>{{ goal }}</em></p>"
            "<p><strong>{{ stake_formatted }}</strong> released back to your card. "
            "Nothing was donated.</p>"
            "<p><a href='{{ app_url }}/wagers/{{ wager_id }}'>View wager →</a></p>"
        ),
        text=(
            "You won.\n\nGoal: {{ goal }}\n\n"
            "{{ stake_formatted }} released back to your card. Nothing was donated.\n"
            "View: {{ app_url }}/wagers/{{ wager_id }}\n"
        ),
        transactional=True,
        required_vars=("goal", "stake_formatted", "app_url", "wager_id"),
    ),
    "wager_lost": Template(
        name="wager_lost",
        subject="You lost. {{ stake_formatted }} → {{ anti_charity_name }}",
        html=_wrap(
            "<h1 style='margin-top:0'>You lost.</h1>"
            "<p>Goal: <em>{{ goal }}</em></p>"
            "<p>We captured <strong>{{ stake_formatted }}</strong> and donated it to "
            "<strong>{{ anti_charity_name }}</strong> — the charity you said you "
            "couldn't stand. That was the deal.</p>"
            "<p><a href='{{ app_url }}/wagers/{{ wager_id }}'>Receipt →</a></p>"
        ),
        text=(
            "You lost.\n\nGoal: {{ goal }}\n\n"
            "{{ stake_formatted }} captured and donated to {{ anti_charity_name }}.\n"
            "Receipt: {{ app_url }}/wagers/{{ wager_id }}\n"
        ),
        transactional=True,
        required_vars=(
            "goal",
            "stake_formatted",
            "anti_charity_name",
            "app_url",
            "wager_id",
        ),
    ),
    "couples_invite": Template(
        name="couples_invite",
        subject="{{ inviter_name }} wants to argue with you (constructively)",
        html=_wrap(
            "<h1 style='margin-top:0'>You've been invited.</h1>"
            "<p><strong>{{ inviter_name }}</strong> created a Couples link on Quarrel "
            "— a shared chat with an AI mediator that doesn't pick sides.</p>"
            "<p>Cross-fact retrieval (using each other's tracked statements during "
            "mediation) stays off until both of you explicitly opt in.</p>"
            "<p><a href='{{ accept_url }}' style='display:inline-block;background:#fafafa;"
            "color:#0a0a0a;padding:12px 24px;border-radius:8px;text-decoration:none;"
            "font-weight:500'>Accept invitation</a></p>"
            "<p style='color:#9ca3af;font-size:12px'>Link expires {{ expires_at }}.</p>"
        ),
        text=(
            "{{ inviter_name }} invited you to a Couples link on Quarrel.\n\n"
            "Accept: {{ accept_url }}\n\nExpires: {{ expires_at }}\n"
        ),
        transactional=True,
        required_vars=("inviter_name", "accept_url", "expires_at"),
    ),
    "couples_dispute_created": Template(
        name="couples_dispute_created",
        subject="{{ sender_name }} opened a dispute: {{ dispute_title }}",
        html=_wrap(
            "<h1 style='margin-top:0'>{{ sender_name }} opened a dispute.</h1>"
            "<p><strong>Subject:</strong> {{ dispute_title }}</p>"
            "<p>They've written their side. Quarrel won't render a verdict "
            "until you add yours — your perspective is what unblocks the AI "
            "mediator.</p>"
            "<p><a href='{{ dispute_url }}' style='display:inline-block;"
            "background:#fafafa;color:#0a0a0a;padding:12px 24px;"
            "border-radius:8px;text-decoration:none;font-weight:500'>"
            "Add your perspective</a></p>"
        ),
        text=(
            "{{ sender_name }} opened a dispute on Quarrel.\n\n"
            "Subject: {{ dispute_title }}\n\n"
            "Add your perspective to unblock the verdict: {{ dispute_url }}\n"
        ),
        transactional=True,
        required_vars=("sender_name", "dispute_title", "dispute_url"),
    ),
    "data_export_ready": Template(
        name="data_export_ready",
        subject="Your Quarrel data export is ready",
        html=_wrap(
            "<h1 style='margin-top:0'>Your export is ready.</h1>"
            "<p>Download a JSON of everything Quarrel holds about you. The link "
            "expires in <strong>{{ ttl_hours }} hours</strong>.</p>"
            "<p><a href='{{ download_url }}'>Download →</a></p>"
        ),
        text=(
            "Your Quarrel data export is ready.\n\n"
            "Download (expires in {{ ttl_hours }} hours):\n{{ download_url }}\n"
        ),
        transactional=True,
        required_vars=("download_url", "ttl_hours"),
    ),
    "account_deletion_grace_started": Template(
        name="account_deletion_grace_started",
        subject="Your Quarrel account will be deleted on {{ delete_on }}",
        html=_wrap(
            "<h1 style='margin-top:0'>Account deletion queued.</h1>"
            "<p>Your account, your facts, your conversations, and your contradictions "
            "will all be hard-deleted on <strong>{{ delete_on }}</strong>.</p>"
            "<p>If this wasn't you — or you change your mind — "
            "<a href='{{ app_url }}/settings/data'>cancel deletion any time before "
            "then</a>.</p>"
        ),
        text=(
            "Account deletion queued.\n\n"
            "Hard delete on {{ delete_on }}.\n"
            "Cancel: {{ app_url }}/settings/data\n"
        ),
        transactional=True,
        required_vars=("delete_on", "app_url"),
    ),
    "emergency_contact_notification": Template(
        name="emergency_contact_notification",
        subject="A Quarrel user listed you as their emergency contact",
        html=_wrap(
            "<h1 style='margin-top:0'>Someone you know may need a check-in.</h1>"
            "<p><strong>{{ user_display_name }}</strong> listed you as their "
            "emergency contact on Quarrel. We're reaching out because they've "
            "expressed clear crisis signals more than once in the last 24 hours.</p>"
            "<p>We don't share what they wrote. We're just letting you know they "
            "might appreciate a call or a message right now.</p>"
            "<p>If you don't want to be listed as their contact, please ask them "
            "to remove you, or reply to this email.</p>"
        ),
        text=(
            "{{ user_display_name }} listed you as their emergency contact on Quarrel.\n\n"
            "We're reaching out because they've expressed clear crisis signals more "
            "than once in the last 24 hours. We don't share what they wrote — just "
            "letting you know they might appreciate hearing from you.\n"
        ),
        transactional=True,
        required_vars=("user_display_name",),
    ),
    "mirror_report_ready": Template(
        name="mirror_report_ready",
        subject="Your Mirror Report is ready. It's not flattering.",
        html=_wrap(
            "<h1 style='margin-top:0'>Mirror Report — week of {{ week_label }}</h1>"
            "<p>Seven days of patterns, dodges, and the themes you kept circling.</p>"
            "<p><a href='{{ app_url }}/mirror'>Read it →</a></p>"
        ),
        text=(
            "Mirror Report — week of {{ week_label }}.\n"
            "Open: {{ app_url }}/mirror\n"
        ),
        transactional=False,
        required_vars=("week_label", "app_url"),
    ),
    "eulogy_ready": Template(
        name="eulogy_ready",
        subject="Your Q{{ quarter }} eulogy is ready.",
        html=_wrap(
            "<h1 style='margin-top:0'>Q{{ quarter }} eulogy</h1>"
            "<p>Three months of what you said you'd do vs what you actually did. "
            "Open it when you're ready to be honest.</p>"
            "<p><a href='{{ app_url }}/eulogy'>Read →</a></p>"
        ),
        text=(
            "Q{{ quarter }} eulogy is ready.\n"
            "Open: {{ app_url }}/eulogy\n"
        ),
        transactional=False,
        required_vars=("quarter", "app_url"),
    ),
    "moderation_rejection": Template(
        name="moderation_rejection",
        subject="Quarrel: your {{ entity_type }} was rejected",
        html=_wrap(
            "<h1 style='margin-top:0'>{{ entity_type|capitalize }} not approved.</h1>"
            "<p>Your {{ entity_type }} — <em>{{ entity_label }}</em> — didn't pass moderation.</p>"
            "<p><strong>Reason:</strong> {{ reason }}</p>"
            "<p>You can edit and resubmit any time.</p>"
        ),
        text=(
            "Your {{ entity_type }} — {{ entity_label }} — wasn't approved.\n\n"
            "Reason: {{ reason }}\n\n"
            "You can edit and resubmit any time.\n"
        ),
        transactional=True,
        required_vars=("entity_type", "entity_label", "reason"),
    ),
    "beta_invite": Template(
        name="beta_invite",
        subject="You're in for the Quarrel beta",
        html=_wrap(
            "<h1 style='margin-top:0'>You're in.</h1>"
            "<p>Quarrel is in closed beta. We hand-picked a small group of "
            "people we think will press hard on the product — you're one of "
            "them.</p>"
            "<p><a href='{{ signup_url }}' style='display:inline-block;"
            "background:#0a0a0a;color:#fafafa;padding:12px 24px;border-radius:"
            "8px;text-decoration:none;font-weight:500'>Open Quarrel</a></p>"
            "<p style='color:#6b7280;font-size:13px'>The link signs you in "
            "without a password. It expires in 24 hours; reply to this email "
            "if it lapses and we'll send another.</p>"
            "<p style='color:#6b7280;font-size:13px'>What we want from you: "
            "tell us when Quarrel is too soft, when it's too cruel, and when "
            "it forgets something it shouldn't have.</p>"
        ),
        text=(
            "You're in. Quarrel is in closed beta.\n\n"
            "Open: {{ signup_url }}\n\n"
            "The link signs you in without a password. It expires in 24 "
            "hours; reply to this email if it lapses and we'll send another.\n\n"
            "What we want from you: tell us when Quarrel is too soft, when "
            "it's too cruel, and when it forgets something it shouldn't "
            "have.\n"
        ),
        transactional=True,
        required_vars=("signup_url",),
    ),
}


# ----- Render --------------------------------------------------------------


_env = Environment(
    autoescape=True,
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


@dataclass(slots=True)
class RenderedEmail:
    subject: str
    html: str
    text: str


def render(template: TemplateName, variables: dict[str, Any]) -> RenderedEmail:
    """Render the named template against `variables`. Raises on missing keys."""

    tpl = TEMPLATES[template]
    settings = get_settings()
    base_vars: dict[str, Any] = {
        "support_email": settings.support_email,
        "legal_address": settings.legal_address,
        "app_url": str(settings.app_url).rstrip("/"),
    }
    merged = {**base_vars, **variables}

    subject = _env.from_string(tpl.subject).render(**merged)
    body_html = _env.from_string(tpl.html).render(**merged)
    body_text = _env.from_string(tpl.text).render(**merged)

    if tpl.transactional:
        footer_html = _FOOTER_HTML_TRANSACTIONAL.format(
            support_email=settings.support_email,
            legal_address=settings.legal_address,
        )
        footer_text = _FOOTER_TEXT_TRANSACTIONAL.format(
            support_email=settings.support_email,
            legal_address=settings.legal_address,
        )
    else:
        unsubscribe_url = merged.get(
            "unsubscribe_url", f"{base_vars['app_url']}/settings/notifications"
        )
        footer_html = _FOOTER_HTML_MARKETING.format(
            unsubscribe_url=unsubscribe_url,
            support_email=settings.support_email,
            legal_address=settings.legal_address,
        )
        footer_text = _FOOTER_TEXT_MARKETING.format(
            unsubscribe_url=unsubscribe_url,
            support_email=settings.support_email,
            legal_address=settings.legal_address,
        )

    return RenderedEmail(
        subject=subject,
        html=body_html.replace("</div></body></html>", footer_html + "</div></body></html>"),
        text=body_text + footer_text,
    )


# ----- Send ----------------------------------------------------------------


@dataclass(slots=True)
class SendResult:
    status: Literal["sent", "skipped", "dry_run", "failed"]
    message_id: str | None = None
    reason: str | None = None


def _hash_email(address: str) -> str:
    return hmac.new(
        b"email-log-hash",
        address.lower().strip().encode(),
        hashlib.sha256,
    ).hexdigest()[:16]


async def _idempotency_seen(
    supabase: AsyncClient, *, key: str
) -> bool:
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
    template: TemplateName,
    user_id: str | None,
    payload_hash: str,
    response_status: int,
    response_body: dict[str, Any] | None,
) -> None:
    await (
        supabase.table("idempotency_keys")
        .insert(
            {
                "key": key,
                "scope": f"email:{template}",
                "user_id": user_id,
                "payload_hash": payload_hash,
                "response_status": response_status,
                "response_body": response_body,
                "expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
            }
        )
        .execute()
    )


async def send_email(
    *,
    template: TemplateName,
    to_email: str,
    variables: dict[str, Any],
    to_name: str | None = None,
    idempotency_key: str | None = None,
    user_id: str | None = None,
    supabase: AsyncClient | None = None,
    client: httpx.AsyncClient | None = None,
) -> SendResult:
    """Render + ship via Resend. Idempotent when key is supplied."""

    settings = get_settings()
    sb = supabase or await get_supabase()

    if idempotency_key is not None and await _idempotency_seen(sb, key=idempotency_key):
        log.info(
            "email.skipped_idempotent",
            template=template,
            to_hash=_hash_email(to_email),
            key=idempotency_key,
        )
        return SendResult(status="skipped", reason="idempotent")

    rendered = render(template, variables)
    to_field = f"{to_name} <{to_email}>" if to_name else to_email
    payload_hash = hmac.new(
        b"email-payload-hash",
        f"{template}:{to_email}:{rendered.subject}".encode(),
        hashlib.sha256,
    ).hexdigest()

    # Dev / test mode — no API key configured.
    if not settings.resend_api_key:
        log.info(
            "email.dry_run",
            template=template,
            to_hash=_hash_email(to_email),
            subject=rendered.subject,
        )
        if idempotency_key is not None:
            await _idempotency_record(
                sb,
                key=idempotency_key,
                template=template,
                user_id=user_id,
                payload_hash=payload_hash,
                response_status=0,
                response_body={"dry_run": True},
            )
        return SendResult(status="dry_run", reason="no_api_key")

    body = {
        "from": settings.resend_from_email,
        "to": [to_field],
        "subject": rendered.subject,
        "html": rendered.html,
        "text": rendered.text,
    }
    headers = {
        "authorization": f"Bearer {settings.resend_api_key}",
        "content-type": "application/json",
    }

    own_client = client is None
    http = client or httpx.AsyncClient(timeout=15.0)
    try:
        resp = await http.post(
            "https://api.resend.com/emails",
            headers=headers,
            json=body,
        )
        if resp.status_code >= 400:
            log.warning(
                "email.send_failed",
                template=template,
                to_hash=_hash_email(to_email),
                status=resp.status_code,
            )
            return SendResult(
                status="failed",
                reason=f"resend_{resp.status_code}",
            )
        parsed = resp.json() if resp.content else {}
        message_id = parsed.get("id") if isinstance(parsed, dict) else None
        log.info(
            "email.sent",
            template=template,
            to_hash=_hash_email(to_email),
            message_id=message_id,
        )
        if idempotency_key is not None:
            await _idempotency_record(
                sb,
                key=idempotency_key,
                template=template,
                user_id=user_id,
                payload_hash=payload_hash,
                response_status=resp.status_code,
                response_body={"id": message_id} if message_id else None,
            )
        return SendResult(status="sent", message_id=message_id)
    except httpx.HTTPError as err:
        log.warning(
            "email.network_error",
            template=template,
            to_hash=_hash_email(to_email),
            error=str(err),
        )
        return SendResult(status="failed", reason="network")
    finally:
        if own_client:
            await http.aclose()


__all__ = [
    "TEMPLATES",
    "RenderedEmail",
    "SendResult",
    "Template",
    "TemplateName",
    "render",
    "send_email",
]
