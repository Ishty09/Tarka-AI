"""POST /couples/disputes/:dispute_id/arbitrate

Called by apps/web's couples server action once both perspectives are
submitted. We re-load the row inside workers (don't trust the caller's
payload), confirm both perspectives are in, and call the arbitrator.

Per CLAUDE.md §1.4, every LLM call stays inside workers. Web is the
trust boundary that delegates here via WORKERS_INTERNAL_SECRET.
"""

from __future__ import annotations

import hashlib
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Path, status
from pydantic import BaseModel

from app.config import get_settings
from app.services._db_typing import row_or_none
from app.services.conversation_prep import PrepError, generate_prep
from app.services.dispute_arbitrator import ArbitrationError, arbitrate
from app.services.email import send_email
from app.services.push import deliver_to_user
from app.services.supabase_client import get_supabase

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/couples", tags=["couples"])


def _verify_internal_caller(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    settings = get_settings()
    if not settings.workers_internal_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "internal_secret_unset")
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing_bearer")
    if authorization.removeprefix("Bearer ").strip() != settings.workers_internal_secret:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_token")


class ArbitrateResponse(BaseModel):
    ok: bool
    status: str
    verdict: dict[str, Any] | None = None
    error: str | None = None


@router.post(
    "/disputes/{dispute_id}/arbitrate",
    response_model=ArbitrateResponse,
    dependencies=[Depends(_verify_internal_caller)],
)
async def arbitrate_dispute(
    dispute_id: str = Path(..., min_length=36, max_length=36),
) -> ArbitrateResponse:
    supabase = await get_supabase()

    row = row_or_none(
        await (
            supabase.table("couple_disputes")
            .select(
                "id, couple_link_id, status, title, "
                "perspective_a_text, perspective_a_user_id, perspective_a_submitted_at, "
                "perspective_b_text, perspective_b_user_id, perspective_b_submitted_at, "
                "arbitration"
            )
            .eq("id", dispute_id)
            .single()
            .execute()
        )
    )

    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dispute not found")

    if row.get("arbitration") and row["status"] == "arbitrated":
        # Idempotent: already arbitrated, return existing verdict.
        return ArbitrateResponse(
            ok=True, status="arbitrated", verdict=row["arbitration"]
        )

    a_text = row.get("perspective_a_text")
    b_text = row.get("perspective_b_text")
    if not a_text or not b_text:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "both perspectives required before arbitration",
        )

    # Stamp arbitrating state so concurrent calls bounce off the check above
    # (will return early with the verdict once one wins the race).
    await (
        supabase.table("couple_disputes")
        .update({"status": "arbitrating"})
        .eq("id", dispute_id)
        .execute()
    )

    try:
        result = await arbitrate(
            perspective_a=a_text,
            perspective_b=b_text,
            couple_link_id=row["couple_link_id"],
            user_a_id=row["perspective_a_user_id"] or "anonymous",
        )
    except ArbitrationError as err:
        log.warning(
            "dispute.arbitration_failed",
            dispute_id=dispute_id,
            error=str(err),
        )
        # Revert status so the user can retry.
        await (
            supabase.table("couple_disputes")
            .update({"status": "awaiting"})
            .eq("id", dispute_id)
            .execute()
        )
        return ArbitrateResponse(ok=False, status="awaiting", error=str(err))

    await (
        supabase.table("couple_disputes")
        .update(
            {
                "status": "arbitrated",
                "arbitration": result.verdict,
                "arbitrated_at": "now()",
                "arbitration_model": result.model,
            }
        )
        .eq("id", dispute_id)
        .execute()
    )

    log.info(
        "dispute.arbitrated",
        dispute_id=dispute_id,
        confidence=result.verdict.get("confidence"),
        who_escalated=result.verdict.get("who_escalated_first"),
    )

    # Notify both partners. Best-effort — failures don't change the
    # arbitration result we return.
    try:
        await _notify_dispute_arbitrated(
            supabase,
            dispute_id=dispute_id,
            couple_link_id=row["couple_link_id"],
            dispute_title=row.get("title") or "(untitled)",
        )
    except Exception as err:  # pragma: no cover - non-fatal
        log.warning(
            "dispute.arbitrated_notify_failed",
            dispute_id=dispute_id,
            error=str(err),
        )

    return ArbitrateResponse(
        ok=True, status="arbitrated", verdict=result.verdict
    )


# ----- Pre-conversation coaching (§9.3.x Week 5) -----------------------------


class GeneratePrepResponse(BaseModel):
    ok: bool
    status: str
    prep: dict[str, Any] | None = None
    error: str | None = None


@router.post(
    "/preps/{prep_id}/generate",
    response_model=GeneratePrepResponse,
    dependencies=[Depends(_verify_internal_caller)],
)
async def generate_conversation_prep(
    prep_id: str = Path(..., min_length=36, max_length=36),
) -> GeneratePrepResponse:
    supabase = await get_supabase()

    row = row_or_none(
        await (
            supabase.table("couple_conversation_preps")
            .select(
                "id, couple_link_id, user_id, topic, desired_outcome, context, status, prep"
            )
            .eq("id", prep_id)
            .single()
            .execute()
        )
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "prep not found")

    if row.get("prep") and row["status"] == "ready":
        return GeneratePrepResponse(ok=True, status="ready", prep=row["prep"])

    await (
        supabase.table("couple_conversation_preps")
        .update({"status": "generating"})
        .eq("id", prep_id)
        .execute()
    )

    try:
        result = await generate_prep(
            user_id=row["user_id"],
            couple_link_id=row["couple_link_id"],
            topic=row["topic"],
            desired_outcome=row.get("desired_outcome"),
            context=row.get("context"),
        )
    except PrepError as err:
        log.warning("conversation_prep.failed", prep_id=prep_id, error=str(err))
        await (
            supabase.table("couple_conversation_preps")
            .update({"status": "failed"})
            .eq("id", prep_id)
            .execute()
        )
        return GeneratePrepResponse(ok=False, status="failed", error=str(err))

    await (
        supabase.table("couple_conversation_preps")
        .update(
            {
                "status": "ready",
                "prep": result.prep,
                "generated_at": "now()",
                "generation_model": result.model,
            }
        )
        .eq("id", prep_id)
        .execute()
    )

    # Best-effort push + email to the prep's owner. Failures don't
    # change the GenerateResponse — the prep itself is saved.
    try:
        await _notify_prep_ready(
            supabase,
            prep_id=prep_id,
            user_id=row["user_id"],
            couple_link_id=row["couple_link_id"],
            topic=row["topic"],
        )
    except Exception as err:  # pragma: no cover - non-fatal
        log.warning(
            "conversation_prep.notify_failed", prep_id=prep_id, error=str(err)
        )

    return GeneratePrepResponse(ok=True, status="ready", prep=result.prep)


# ----- Notify partner of new dispute ----------------------------------------


class NotifyResponse(BaseModel):
    ok: bool
    delivered: dict[str, bool]


@router.post(
    "/disputes/{dispute_id}/notify-created",
    response_model=NotifyResponse,
    dependencies=[Depends(_verify_internal_caller)],
)
async def notify_dispute_created(
    dispute_id: str = Path(..., min_length=36, max_length=36),
) -> NotifyResponse:
    """Fire push + email to the partner who hasn't submitted yet.

    Best-effort: returns delivered flags but never raises if a channel
    fails. The web action calls this fire-and-forget; failures don't
    block dispute creation.

    Idempotency: keyed on the dispute_id so retries don't double-notify.
    Push uses scope `push:couples_dispute_created`; email uses
    `email:couples_dispute_created:<dispute_id>`.
    """

    supabase = await get_supabase()

    row = row_or_none(
        await (
            supabase.table("couple_disputes")
            .select(
                "id, couple_link_id, title, "
                "perspective_a_user_id, perspective_a_text, "
                "perspective_b_user_id, perspective_b_text"
            )
            .eq("id", dispute_id)
            .single()
            .execute()
        )
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dispute not found")

    # The "sender" is the user who submitted a perspective; the "partner"
    # is the other slot on the link who still needs to submit. If both
    # slots are filled there's no one to notify.
    sender_id = row.get("perspective_a_user_id") or row.get("perspective_b_user_id")
    if not sender_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "no perspective submitted")
    if row.get("perspective_a_text") and row.get("perspective_b_text"):
        return NotifyResponse(ok=True, delivered={"push": False, "email": False})

    link = row_or_none(
        await (
            supabase.table("couple_links")
            .select("user_a, user_b, status")
            .eq("id", row["couple_link_id"])
            .single()
            .execute()
        )
    )
    if link is None or link.get("status") != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "couple link inactive")

    partner_id = link["user_b"] if sender_id == link["user_a"] else link["user_a"]
    if not partner_id:
        # Pending invite — partner slot not yet filled. Nothing to do.
        return NotifyResponse(ok=True, delivered={"push": False, "email": False})

    sender_profile = row_or_none(
        await (
            supabase.table("profiles")
            .select("display_name, username")
            .eq("id", sender_id)
            .single()
            .execute()
        )
    )
    sender_name = "Your partner"
    if sender_profile:
        sender_name = (
            sender_profile.get("display_name")
            or sender_profile.get("username")
            or sender_name
        )

    # Email lives on auth.users — fetched via admin client. Profile
    # notification_email respect is handled inside send_email.
    partner_email: str | None = None
    try:
        res = await supabase.auth.admin.get_user_by_id(partner_id)
        user_obj = getattr(res, "user", None) or getattr(res, "data", None)
        email_val = getattr(user_obj, "email", None) if user_obj else None
        if isinstance(email_val, str) and email_val:
            partner_email = email_val
    except Exception as err:  # pragma: no cover - non-fatal
        log.info("couples.notify.email_lookup_failed", error=str(err))

    settings = get_settings()
    dispute_url = (
        f"{str(settings.app_url).rstrip('/')}"
        f"/couples/{row['couple_link_id']}/disputes/{dispute_id}"
    )
    title = row.get("title") or "(untitled)"

    delivered = {"push": False, "email": False}

    try:
        results = await deliver_to_user(
            user_id=partner_id,
            template="couples_dispute_created",
            variables={"sender_name": sender_name, "dispute_title": title},
            deep_link=dispute_url,
            idempotency_key=f"push:couples_dispute_created:{dispute_id}",
            supabase=supabase,
        )
        delivered["push"] = any(r.status in ("sent", "dry_run") for r in results)
    except Exception as err:  # pragma: no cover - non-fatal
        log.warning("couples.notify.push_failed", dispute_id=dispute_id, error=str(err))

    if partner_email:
        try:
            await send_email(
                template="couples_dispute_created",
                to_email=partner_email,
                variables={
                    "sender_name": sender_name,
                    "dispute_title": title,
                    "dispute_url": dispute_url,
                },
                user_id=partner_id,
                idempotency_key=f"email:couples_dispute_created:{dispute_id}",
                supabase=supabase,
            )
            delivered["email"] = True
        except Exception as err:  # pragma: no cover - non-fatal
            log.warning("couples.notify.email_failed", dispute_id=dispute_id, error=str(err))

    log.info(
        "couples.dispute_created.notified",
        dispute_id=dispute_id,
        partner_id=partner_id,
        delivered=delivered,
    )
    return NotifyResponse(ok=True, delivered=delivered)


# ----- Notify creator when partner adds their perspective ------------------


@router.post(
    "/disputes/{dispute_id}/notify-perspective-added",
    response_model=NotifyResponse,
    dependencies=[Depends(_verify_internal_caller)],
)
async def notify_perspective_added(
    dispute_id: str = Path(..., min_length=36, max_length=36),
) -> NotifyResponse:
    """Fire push + email to the original creator when the second
    perspective arrives, signalling that the arbitration LLM is now
    running. Idempotent on dispute_id.

    Determines who the "creator" is by comparing submitted_at on the
    two perspective slots — earlier timestamp wins. Both timestamps
    must be set; if either is missing we treat it as a no-op so a
    misfire during the single-perspective phase can't surprise anyone.
    """

    supabase = await get_supabase()

    row = row_or_none(
        await (
            supabase.table("couple_disputes")
            .select(
                "id, couple_link_id, title, "
                "perspective_a_user_id, perspective_a_submitted_at, "
                "perspective_b_user_id, perspective_b_submitted_at"
            )
            .eq("id", dispute_id)
            .single()
            .execute()
        )
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dispute not found")

    a_at = row.get("perspective_a_submitted_at")
    b_at = row.get("perspective_b_submitted_at")
    a_uid = row.get("perspective_a_user_id")
    b_uid = row.get("perspective_b_user_id")
    if not (a_at and b_at and a_uid and b_uid):
        # Only one side in — nothing to notify yet.
        return NotifyResponse(ok=True, delivered={"push": False, "email": False})

    # Earlier timestamp = creator (the one waiting). Later = answerer.
    if a_at <= b_at:
        creator_id, answerer_id = a_uid, b_uid
    else:
        creator_id, answerer_id = b_uid, a_uid

    answerer_profile = row_or_none(
        await (
            supabase.table("profiles")
            .select("display_name, username")
            .eq("id", answerer_id)
            .single()
            .execute()
        )
    )
    partner_name = "Your partner"
    if answerer_profile:
        partner_name = (
            answerer_profile.get("display_name")
            or answerer_profile.get("username")
            or partner_name
        )

    settings = get_settings()
    dispute_url = (
        f"{str(settings.app_url).rstrip('/')}"
        f"/couples/{row['couple_link_id']}/disputes/{dispute_id}"
    )
    title = row.get("title") or "(untitled)"

    delivered = {"push": False, "email": False}

    try:
        results = await deliver_to_user(
            user_id=creator_id,
            template="couples_dispute_perspective_added",
            variables={"partner_name": partner_name, "dispute_title": title},
            deep_link=dispute_url,
            idempotency_key=f"push:couples_dispute_perspective_added:{dispute_id}",
            supabase=supabase,
        )
        delivered["push"] = any(r.status in ("sent", "dry_run") for r in results)
    except Exception as err:  # pragma: no cover - non-fatal
        log.warning("couples.notify.persp_push_failed", dispute_id=dispute_id, error=str(err))

    creator_email = await _resolve_email(supabase, creator_id)
    if creator_email:
        try:
            await send_email(
                template="couples_dispute_perspective_added",
                to_email=creator_email,
                variables={
                    "partner_name": partner_name,
                    "dispute_title": title,
                    "dispute_url": dispute_url,
                },
                user_id=creator_id,
                idempotency_key=f"email:couples_dispute_perspective_added:{dispute_id}",
                supabase=supabase,
            )
            delivered["email"] = True
        except Exception as err:  # pragma: no cover - non-fatal
            log.warning("couples.notify.persp_email_failed", dispute_id=dispute_id, error=str(err))

    log.info(
        "couples.perspective_added.notified",
        dispute_id=dispute_id,
        creator_id=creator_id,
        delivered=delivered,
    )
    return NotifyResponse(ok=True, delivered=delivered)


# ----- Notify both partners when arbitration completes ---------------------


async def _resolve_email(supabase: Any, user_id: str) -> str | None:
    try:
        res = await supabase.auth.admin.get_user_by_id(user_id)
    except Exception as err:  # pragma: no cover - non-fatal
        log.info("couples.email_lookup_failed", user_id=user_id, error=str(err))
        return None
    user_obj = getattr(res, "user", None) or getattr(res, "data", None)
    email_val = getattr(user_obj, "email", None) if user_obj else None
    return email_val if isinstance(email_val, str) and email_val else None


async def _notify_dispute_arbitrated(
    supabase: Any,
    *,
    dispute_id: str,
    couple_link_id: str,
    dispute_title: str,
) -> None:
    """Push + email to BOTH partners when the verdict lands.

    Idempotency keys are per-user so retries don't double-notify either
    side. Per-channel try/except keeps a single broken delivery from
    sinking the others.
    """

    link = row_or_none(
        await (
            supabase.table("couple_links")
            .select("user_a, user_b")
            .eq("id", couple_link_id)
            .single()
            .execute()
        )
    )
    if link is None:
        return

    settings = get_settings()
    dispute_url = (
        f"{str(settings.app_url).rstrip('/')}"
        f"/couples/{couple_link_id}/disputes/{dispute_id}"
    )

    for user_id in (link.get("user_a"), link.get("user_b")):
        if not user_id:
            continue
        try:
            await deliver_to_user(
                user_id=user_id,
                template="couples_dispute_arbitrated",
                variables={"dispute_title": dispute_title},
                deep_link=dispute_url,
                idempotency_key=f"push:couples_dispute_arbitrated:{dispute_id}:{user_id}",
                supabase=supabase,
            )
        except Exception as err:  # pragma: no cover - non-fatal
            log.warning(
                "couples.arbitrated_notify.push_failed",
                user_id=user_id,
                error=str(err),
            )

        email_addr = await _resolve_email(supabase, user_id)
        if not email_addr:
            continue
        try:
            await send_email(
                template="couples_dispute_arbitrated",
                to_email=email_addr,
                variables={
                    "dispute_title": dispute_title,
                    "dispute_url": dispute_url,
                },
                user_id=user_id,
                idempotency_key=f"email:couples_dispute_arbitrated:{dispute_id}:{user_id}",
                supabase=supabase,
            )
        except Exception as err:  # pragma: no cover - non-fatal
            log.warning(
                "couples.arbitrated_notify.email_failed",
                user_id=user_id,
                error=str(err),
            )


# ----- Notify prep owner when async generation finishes --------------------


async def _notify_prep_ready(
    supabase: Any,
    *,
    prep_id: str,
    user_id: str,
    couple_link_id: str,
    topic: str,
) -> None:
    """Push + email the prep owner. Preps are private — only the user
    who created them ever sees them, so we never notify the partner.
    Idempotency keyed on prep_id.
    """

    app_url = str(get_settings().app_url).rstrip("/")
    prep_url = f"{app_url}/couples/{couple_link_id}/preps/{prep_id}"

    try:
        await deliver_to_user(
            user_id=user_id,
            template="couples_prep_ready",
            variables={"topic": topic},
            deep_link=prep_url,
            idempotency_key=f"push:couples_prep_ready:{prep_id}",
            supabase=supabase,
        )
    except Exception as err:  # pragma: no cover - non-fatal
        log.warning(
            "couples.prep_ready.push_failed", prep_id=prep_id, error=str(err)
        )

    email_addr = await _resolve_email(supabase, user_id)
    if not email_addr:
        return
    try:
        await send_email(
            template="couples_prep_ready",
            to_email=email_addr,
            variables={"topic": topic, "prep_url": prep_url},
            user_id=user_id,
            idempotency_key=f"email:couples_prep_ready:{prep_id}",
            supabase=supabase,
        )
    except Exception as err:  # pragma: no cover - non-fatal
        log.warning(
            "couples.prep_ready.email_failed", prep_id=prep_id, error=str(err)
        )


# ----- Email an invite to the partner --------------------------------------


class EmailInviteRequest(BaseModel):
    partner_email: str


class EmailInviteResponse(BaseModel):
    ok: bool
    sent: bool


@router.post(
    "/invites/{link_id}/email",
    response_model=EmailInviteResponse,
    dependencies=[Depends(_verify_internal_caller)],
)
async def email_couple_invite(
    body: EmailInviteRequest,
    link_id: str = Path(..., min_length=36, max_length=36),
) -> EmailInviteResponse:
    """Send the couples_invite email to a partner the creator named.

    The web action creates the link with status='pending' and an
    invite_code, then fires this endpoint fire-and-forget. We re-load
    the link to get the canonical code + expires_at so a tampered web
    payload can't smuggle stale data.

    Idempotency: keyed on (link_id, partner_email). Re-issuing the
    same invite to the same email is a no-op.
    """

    supabase = await get_supabase()

    link = row_or_none(
        await (
            supabase.table("couple_links")
            .select("id, user_a, status, invite_code, invite_expires_at")
            .eq("id", link_id)
            .single()
            .execute()
        )
    )
    if link is None or link.get("status") != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "invite not pending")
    invite_code = link.get("invite_code")
    if not isinstance(invite_code, str) or not invite_code:
        raise HTTPException(status.HTTP_409_CONFLICT, "invite already burned")

    # Inviter name — prefer display_name, fall back to username, then a
    # neutral placeholder so the email subject still reads naturally.
    inviter_profile = row_or_none(
        await (
            supabase.table("profiles")
            .select("display_name, username")
            .eq("id", link["user_a"])
            .single()
            .execute()
        )
    )
    inviter_name = "Someone you know"
    if inviter_profile:
        inviter_name = (
            inviter_profile.get("display_name")
            or inviter_profile.get("username")
            or inviter_name
        )

    settings = get_settings()
    accept_url = (
        f"{str(settings.app_url).rstrip('/')}/couples/join/{invite_code}"
    )
    expires_raw = link.get("invite_expires_at") or ""
    # Show just the date portion (YYYY-MM-DD) so the email reads cleanly.
    expires_at = str(expires_raw)[:10] if expires_raw else "soon"

    # Hash the partner_email into the idempotency key so re-running the
    # cron / a double-click doesn't double-send to the same partner,
    # but the creator CAN re-issue to a different email if they typo'd
    # the first try.
    email_hash = hashlib.sha256(
        body.partner_email.lower().strip().encode()
    ).hexdigest()[:16]

    try:
        await send_email(
            template="couples_invite",
            to_email=body.partner_email,
            variables={
                "inviter_name": inviter_name,
                "accept_url": accept_url,
                "expires_at": expires_at,
            },
            user_id=link["user_a"],
            idempotency_key=f"email:couples_invite:{link_id}:{email_hash}",
            supabase=supabase,
        )
    except Exception as err:  # pragma: no cover - non-fatal
        log.warning(
            "couples.invite_email.failed", link_id=link_id, error=str(err)
        )
        return EmailInviteResponse(ok=False, sent=False)

    return EmailInviteResponse(ok=True, sent=True)
