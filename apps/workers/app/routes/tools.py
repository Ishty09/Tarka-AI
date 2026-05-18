"""Productivity-tool endpoints (CLAUDE.md §9.1, §9.5).

This module hosts the non-streaming tool routes — Council first; Decision
Killer, Cope Detector, Steelman, etc. land here in subsequent §27 steps.
All routes follow the same web→worker handshake as /chat/stream:
WORKERS_INTERNAL_SECRET + X-User-Id (apps/web is the trust boundary, §22).
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.config import get_settings
from app.prompts.council import DILEMMA_MAX_CHARS
from app.services.council import CouncilWipeoutError, run_council
from app.services.quotas import (
    get_council_quota,
    get_message_quota,
    increment_council_count,
    increment_message_count,
)
from app.services.cope_detector import RATIONALIZATION_MAX_CHARS, run_cope_detector
from app.services.decision_killer import DECISION_MAX_CHARS, run_decision_killer
from app.services.past_self import PAST_CONTENT_MAX_CHARS, run_past_self
from app.services.safety import classify_message
from app.services.steelman import POSITION_MAX_CHARS, run_steelman
from app.services.supabase_client import get_supabase

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/tools", tags=["tools"])


# ----- Auth (shared with /chat/stream) ---------------------------------------


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


# ----- Council ---------------------------------------------------------------


class CouncilRequest(BaseModel):
    dilemma: str = Field(min_length=10, max_length=DILEMMA_MAX_CHARS)


class CouncilReplyPayload(BaseModel):
    slug: str
    text: str | None
    error: str | None = None


class JudgeVerdictPayload(BaseModel):
    conditions_for: list[str]
    conditions_against: list[str]
    missing_information: list[str]
    confidence: int
    verdict: str


class CouncilResponse(BaseModel):
    conversation_id: str
    assistant_message_id: int | None
    replies: list[CouncilReplyPayload]
    verdict: JudgeVerdictPayload


class QuotaExceededResponse(BaseModel):
    error: str
    tier: str
    limit: int
    used: int
    reset_at: str
    upgrade_url: str | None = None


@router.post(
    "/council",
    dependencies=[Depends(_verify_internal_caller)],
    responses={429: {"model": QuotaExceededResponse}},
)
async def council(
    req: CouncilRequest,
    user_id: Annotated[str, Depends(_require_user)],
) -> Any:
    supabase = await get_supabase()

    # Quota first — cheaper than the safety screen if the user has nothing left.
    quota = await get_council_quota(supabase, user_id)
    if quota.exceeded:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "quota_exceeded",
                "tier": quota.tier,
                "limit": quota.limit,
                "used": quota.used,
                "reset_at": quota.reset_at.isoformat(),
                "upgrade_url": "/pricing",
            },
        )

    safety = await classify_message(
        req.dilemma,
        user_id=user_id,
        conversation_id=None,
    )
    if safety.verdict != "safe":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "safety_blocked",
                "verdict": safety.verdict,
                "reason": safety.reason,
            },
        )

    try:
        run = await run_council(supabase, user_id=user_id, dilemma=req.dilemma)
    except CouncilWipeoutError as err:
        log.warning("council.wipeout", user_id=user_id, error=str(err))
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "council_wipeout",
        ) from err

    await increment_council_count(supabase, user_id)

    return CouncilResponse(
        conversation_id=run.conversation_id or "",
        assistant_message_id=run.assistant_message_id,
        replies=[
            CouncilReplyPayload(slug=r.slug, text=r.text, error=r.error)
            for r in run.replies
        ],
        verdict=JudgeVerdictPayload(
            conditions_for=run.verdict.conditions_for,
            conditions_against=run.verdict.conditions_against,
            missing_information=run.verdict.missing_information,
            confidence=run.verdict.confidence,
            verdict=run.verdict.verdict,
        ),
    )


# ----- Steelman -------------------------------------------------------------


class SteelmanRequest(BaseModel):
    position: str = Field(min_length=20, max_length=POSITION_MAX_CHARS)


class SteelmanCounterPayload(BaseModel):
    counter: str
    response: str


class SteelmanResponse(BaseModel):
    conversation_id: str
    assistant_message_id: int | None
    strongest_version: str
    assumptions: list[str]
    evidence: list[str]
    counters: list[SteelmanCounterPayload]


@router.post(
    "/steelman",
    dependencies=[Depends(_verify_internal_caller)],
    responses={429: {"model": QuotaExceededResponse}},
)
async def steelman(
    req: SteelmanRequest,
    user_id: Annotated[str, Depends(_require_user)],
) -> Any:
    supabase = await get_supabase()

    # §9.1.3: counts as 1 message → use the chat-message quota.
    quota = await get_message_quota(supabase, user_id)
    if quota.exceeded:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "quota_exceeded",
                "tier": quota.tier,
                "limit": quota.limit,
                "used": quota.used,
                "reset_at": quota.reset_at.isoformat(),
                "upgrade_url": "/pricing",
            },
        )

    safety = await classify_message(
        req.position,
        user_id=user_id,
        conversation_id=None,
    )
    if safety.verdict != "safe":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "safety_blocked",
                "verdict": safety.verdict,
                "reason": safety.reason,
            },
        )

    run = await run_steelman(supabase, user_id=user_id, position=req.position)
    if run is None:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "steelman_failed")

    await increment_message_count(supabase, user_id)

    return SteelmanResponse(
        conversation_id=run.conversation_id or "",
        assistant_message_id=run.assistant_message_id,
        strongest_version=run.result.strongest_version,
        assumptions=run.result.assumptions,
        evidence=run.result.evidence,
        counters=[
            SteelmanCounterPayload(counter=c.counter, response=c.response)
            for c in run.result.counters
        ],
    )


# ----- Decision Killer ------------------------------------------------------


class DecisionKillerRequest(BaseModel):
    decision: str = Field(min_length=20, max_length=DECISION_MAX_CHARS)


class WrongReasonPayload(BaseModel):
    reason: str
    argument: str


class DecisionKillerResponse(BaseModel):
    conversation_id: str
    assistant_message_id: int | None
    reasons_wrong: list[WrongReasonPayload]
    one_reason_right: str
    actual_avoidance: str


@router.post(
    "/decision-killer",
    dependencies=[Depends(_verify_internal_caller)],
    responses={429: {"model": QuotaExceededResponse}},
)
async def decision_killer(
    req: DecisionKillerRequest,
    user_id: Annotated[str, Depends(_require_user)],
) -> Any:
    supabase = await get_supabase()

    # §9.5.1: counts as 1 message → chat-message quota.
    quota = await get_message_quota(supabase, user_id)
    if quota.exceeded:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "quota_exceeded",
                "tier": quota.tier,
                "limit": quota.limit,
                "used": quota.used,
                "reset_at": quota.reset_at.isoformat(),
                "upgrade_url": "/pricing",
            },
        )

    safety = await classify_message(
        req.decision,
        user_id=user_id,
        conversation_id=None,
    )
    if safety.verdict != "safe":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "safety_blocked",
                "verdict": safety.verdict,
                "reason": safety.reason,
            },
        )

    run = await run_decision_killer(supabase, user_id=user_id, decision=req.decision)
    if run is None:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "decision_killer_failed")

    await increment_message_count(supabase, user_id)

    return DecisionKillerResponse(
        conversation_id=run.conversation_id or "",
        assistant_message_id=run.assistant_message_id,
        reasons_wrong=[
            WrongReasonPayload(reason=r.reason, argument=r.argument)
            for r in run.result.reasons_wrong
        ],
        one_reason_right=run.result.one_reason_right,
        actual_avoidance=run.result.actual_avoidance,
    )


# ----- Cope Detector --------------------------------------------------------


class CopeDetectorRequest(BaseModel):
    rationalization: str = Field(min_length=15, max_length=RATIONALIZATION_MAX_CHARS)


class CopeDetectorResponse(BaseModel):
    conversation_id: str
    assistant_message_id: int | None
    telling_yourself: str
    actually_avoiding: str
    unasked_question: str


@router.post(
    "/cope-detector",
    dependencies=[Depends(_verify_internal_caller)],
    responses={429: {"model": QuotaExceededResponse}},
)
async def cope_detector(
    req: CopeDetectorRequest,
    user_id: Annotated[str, Depends(_require_user)],
) -> Any:
    supabase = await get_supabase()

    # §9.5.2: counts as 1 message → chat-message quota.
    quota = await get_message_quota(supabase, user_id)
    if quota.exceeded:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "quota_exceeded",
                "tier": quota.tier,
                "limit": quota.limit,
                "used": quota.used,
                "reset_at": quota.reset_at.isoformat(),
                "upgrade_url": "/pricing",
            },
        )

    safety = await classify_message(
        req.rationalization,
        user_id=user_id,
        conversation_id=None,
    )
    if safety.verdict != "safe":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "safety_blocked",
                "verdict": safety.verdict,
                "reason": safety.reason,
            },
        )

    run = await run_cope_detector(
        supabase,
        user_id=user_id,
        rationalization=req.rationalization,
    )
    if run is None:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "cope_detector_failed")

    await increment_message_count(supabase, user_id)

    return CopeDetectorResponse(
        conversation_id=run.conversation_id or "",
        assistant_message_id=run.assistant_message_id,
        telling_yourself=run.result.telling_yourself,
        actually_avoiding=run.result.actually_avoiding,
        unasked_question=run.result.unasked_question,
    )


# ----- Past Self ------------------------------------------------------------


class PastSelfRequest(BaseModel):
    past_content: str = Field(min_length=20, max_length=PAST_CONTENT_MAX_CHARS)


class PastSelfResponse(BaseModel):
    conversation_id: str
    assistant_message_id: int | None
    rebuttal: str


@router.post(
    "/past-self",
    dependencies=[Depends(_verify_internal_caller)],
    responses={429: {"model": QuotaExceededResponse}},
)
async def past_self(
    req: PastSelfRequest,
    user_id: Annotated[str, Depends(_require_user)],
) -> Any:
    supabase = await get_supabase()

    # §9.1.5: counts as 1 message per turn.
    quota = await get_message_quota(supabase, user_id)
    if quota.exceeded:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "quota_exceeded",
                "tier": quota.tier,
                "limit": quota.limit,
                "used": quota.used,
                "reset_at": quota.reset_at.isoformat(),
                "upgrade_url": "/pricing",
            },
        )

    safety = await classify_message(
        req.past_content,
        user_id=user_id,
        conversation_id=None,
    )
    if safety.verdict != "safe":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "safety_blocked",
                "verdict": safety.verdict,
                "reason": safety.reason,
            },
        )

    run = await run_past_self(
        supabase,
        user_id=user_id,
        past_content=req.past_content,
    )
    if run is None:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "past_self_failed")

    await increment_message_count(supabase, user_id)

    return PastSelfResponse(
        conversation_id=run.conversation_id or "",
        assistant_message_id=run.assistant_message_id,
        rebuttal=run.rebuttal,
    )
