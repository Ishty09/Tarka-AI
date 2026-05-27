"""Onboarding-triggered worker endpoints.

Called by apps/web's onboarding action when a user finishes the signup
flow. Single endpoint today (welcome email); the route exists as its
own module so future onboarding-finish work has an obvious home
without cluttering chat/couples/admin.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Path, status
from pydantic import BaseModel

from app.config import get_settings
from app.services._db_typing import row_or_none
from app.services.email import send_email
from app.services.supabase_client import get_supabase

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


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


class WelcomeEmailResponse(BaseModel):
    ok: bool
    sent: bool


@router.post(
    "/users/{user_id}/welcome-email",
    response_model=WelcomeEmailResponse,
    dependencies=[Depends(_verify_internal_caller)],
)
async def send_welcome_email(
    user_id: str = Path(..., min_length=36, max_length=36),
) -> WelcomeEmailResponse:
    """Send the welcome email after a user completes onboarding.

    Idempotent on user_id — a re-run after onboarding completion (or
    a double-submit on the legal step) won't double-send.
    """

    supabase = await get_supabase()

    profile_res = (
        await supabase.table("profiles")
        .select("display_name, username")
        .eq("id", user_id)
        .single()
        .execute()
    )
    profile = row_or_none(profile_res.data)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")

    display_name = (
        profile.get("display_name")
        or profile.get("username")
        or "there"
    )

    # Email is on auth.users — not on profiles. Use the admin client.
    try:
        res = await supabase.auth.admin.get_user_by_id(user_id)
    except Exception as err:  # pragma: no cover - non-fatal
        log.info(
            "onboarding.welcome.email_lookup_failed",
            user_id=user_id,
            error=str(err),
        )
        return WelcomeEmailResponse(ok=False, sent=False)
    user_obj = getattr(res, "user", None) or getattr(res, "data", None)
    email_val = getattr(user_obj, "email", None) if user_obj else None
    if not isinstance(email_val, str) or not email_val:
        return WelcomeEmailResponse(ok=False, sent=False)

    try:
        await send_email(
            template="welcome",
            to_email=email_val,
            variables={"display_name": display_name},
            user_id=user_id,
            idempotency_key=f"email:welcome:{user_id}",
            supabase=supabase,
        )
    except Exception as err:  # pragma: no cover - non-fatal
        log.warning(
            "onboarding.welcome.send_failed", user_id=user_id, error=str(err)
        )
        return WelcomeEmailResponse(ok=False, sent=False)

    return WelcomeEmailResponse(ok=True, sent=True)
