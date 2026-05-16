"""Internal safety screen endpoint.

POST /safety/screen — used by apps/web when it needs a server-side screen
without invoking the chat flow (e.g. moderating a roast-feed submission).
The chat route (/chat/stream, Phase B step 9) will call classify_message
directly rather than going through this HTTP hop.

Authenticated via the WORKERS_INTERNAL_SECRET header (§5) — never exposed
to the public internet by Caddy.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.safety import SafetyResult, classify_message, redact

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/safety", tags=["safety"])


def _verify_internal_secret(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Internal-only — must present the shared secret."""

    settings = get_settings()
    if not settings.workers_internal_secret:
        # Misconfigured deploy: fail closed.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "internal_secret_unset")

    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing_bearer")
    token = authorization.removeprefix("Bearer ").strip()
    if token != settings.workers_internal_secret:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_token")


class ScreenRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)
    user_id: str | None = None
    conversation_id: str | None = None


class ScreenResponse(BaseModel):
    result: SafetyResult
    redacted_message: str


@router.post(
    "/screen",
    response_model=ScreenResponse,
    dependencies=[Depends(_verify_internal_secret)],
)
async def screen(req: ScreenRequest) -> ScreenResponse:
    result = await classify_message(
        req.message,
        user_id=req.user_id,
        conversation_id=req.conversation_id,
    )
    redacted = redact(req.message, result.redactions)
    return ScreenResponse(result=result, redacted_message=redacted)
