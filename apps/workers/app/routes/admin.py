"""Admin REST endpoints (CLAUDE.md §4).

All routes require WORKERS_INTERNAL_SECRET + X-User-Id and additionally
assert profiles.is_admin = true. Every write goes through
apps/workers/app/services/admin.py which logs to audit_log.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.admin import (
    NotAdminError,
    list_incidents,
    list_pending_feed_posts,
    list_pending_personas,
    moderate_feed_post,
    moderate_persona,
    require_admin,
    review_incident,
    search_users,
    suspend_user,
    unsuspend_user,
)
from app.services.supabase_client import get_supabase

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


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


def _require_user(
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
) -> str:
    if not x_user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing_user")
    return x_user_id


async def _admin_dep(user_id: Annotated[str, Depends(_require_user)]) -> str:
    supabase = await get_supabase()
    try:
        await require_admin(supabase, user_id=user_id)
    except NotAdminError as err:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not_admin") from err
    return user_id


# ----- Listings ------------------------------------------------------------


@router.get(
    "/personas/pending",
    dependencies=[Depends(_verify_internal_caller)],
)
async def get_pending_personas(
    user_id: Annotated[str, Depends(_admin_dep)],
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    supabase = await get_supabase()
    rows = await list_pending_personas(supabase, limit=limit)
    return {"personas": [row.__dict__ for row in rows]}


@router.get(
    "/feed/pending",
    dependencies=[Depends(_verify_internal_caller)],
)
async def get_pending_feed_posts(
    user_id: Annotated[str, Depends(_admin_dep)],
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    supabase = await get_supabase()
    rows = await list_pending_feed_posts(supabase, limit=limit)
    return {"posts": [row.__dict__ for row in rows]}


@router.get(
    "/incidents",
    dependencies=[Depends(_verify_internal_caller)],
)
async def get_incidents(
    user_id: Annotated[str, Depends(_admin_dep)],
    category: str | None = Query(default=None),
    unreviewed_only: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    supabase = await get_supabase()
    rows = await list_incidents(
        supabase, category=category, unreviewed_only=unreviewed_only, limit=limit
    )
    return {"incidents": [row.__dict__ for row in rows]}


@router.get(
    "/users",
    dependencies=[Depends(_verify_internal_caller)],
)
async def get_users(
    user_id: Annotated[str, Depends(_admin_dep)],
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    supabase = await get_supabase()
    rows = await search_users(supabase, query=q, limit=limit)
    return {"users": [row.__dict__ for row in rows]}


# ----- Mutations -----------------------------------------------------------


class ModeratePersonaRequest(BaseModel):
    persona_id: str
    action: Literal["approve", "reject", "flag"]
    notes: str | None = Field(default=None, max_length=2000)


@router.post(
    "/personas/moderate",
    dependencies=[Depends(_verify_internal_caller)],
)
async def post_moderate_persona(
    req: ModeratePersonaRequest,
    user_id: Annotated[str, Depends(_admin_dep)],
) -> dict[str, str]:
    supabase = await get_supabase()
    actor = await require_admin(supabase, user_id=user_id)
    await moderate_persona(
        supabase,
        actor=actor,
        persona_id=req.persona_id,
        action=req.action,
        notes=req.notes,
    )
    return {"status": "ok"}


class ModerateFeedPostRequest(BaseModel):
    post_id: str
    action: Literal["approve", "reject", "remove"]
    notes: str | None = Field(default=None, max_length=2000)


@router.post(
    "/feed/moderate",
    dependencies=[Depends(_verify_internal_caller)],
)
async def post_moderate_feed_post(
    req: ModerateFeedPostRequest,
    user_id: Annotated[str, Depends(_admin_dep)],
) -> dict[str, str]:
    supabase = await get_supabase()
    actor = await require_admin(supabase, user_id=user_id)
    await moderate_feed_post(
        supabase,
        actor=actor,
        post_id=req.post_id,
        action=req.action,
        notes=req.notes,
    )
    return {"status": "ok"}


class SuspendUserRequest(BaseModel):
    user_id: str
    reason: str = Field(min_length=3, max_length=1000)


@router.post(
    "/users/suspend",
    dependencies=[Depends(_verify_internal_caller)],
)
async def post_suspend_user(
    req: SuspendUserRequest,
    user_id: Annotated[str, Depends(_admin_dep)],
) -> dict[str, str]:
    supabase = await get_supabase()
    actor = await require_admin(supabase, user_id=user_id)
    try:
        await suspend_user(
            supabase, actor=actor, user_id=req.user_id, reason=req.reason
        )
    except PermissionError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err)) from err
    return {"status": "ok"}


class UnsuspendUserRequest(BaseModel):
    user_id: str


@router.post(
    "/users/unsuspend",
    dependencies=[Depends(_verify_internal_caller)],
)
async def post_unsuspend_user(
    req: UnsuspendUserRequest,
    user_id: Annotated[str, Depends(_admin_dep)],
) -> dict[str, str]:
    supabase = await get_supabase()
    actor = await require_admin(supabase, user_id=user_id)
    await unsuspend_user(supabase, actor=actor, user_id=req.user_id)
    return {"status": "ok"}


class ReviewIncidentRequest(BaseModel):
    incident_id: int
    notes: str | None = Field(default=None, max_length=2000)


@router.post(
    "/incidents/review",
    dependencies=[Depends(_verify_internal_caller)],
)
async def post_review_incident(
    req: ReviewIncidentRequest,
    user_id: Annotated[str, Depends(_admin_dep)],
) -> dict[str, str]:
    supabase = await get_supabase()
    actor = await require_admin(supabase, user_id=user_id)
    await review_incident(
        supabase, actor=actor, incident_id=req.incident_id, notes=req.notes
    )
    return {"status": "ok"}
