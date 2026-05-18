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
from app.services.breakup_analyzer import (
    DURATION_MAX_CHARS,
    QUOTA_COST as BREAKUP_QUOTA_COST,
    THREAD_MAX_CHARS,
    run_breakup_analyzer,
)
from app.services.cope_detector import RATIONALIZATION_MAX_CHARS, run_cope_detector
from app.services.decision_killer import DECISION_MAX_CHARS, run_decision_killer
from app.services.future_self import FUTURE_DECISION_MAX_CHARS, run_future_self
from app.services.negotiation import (
    NotANegotiationError,
    UnknownScenarioError,
    list_scenarios,
    run_critique,
    start_session,
)
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


# ----- Future Self ----------------------------------------------------------


class FutureSelfRequest(BaseModel):
    decision: str = Field(min_length=20, max_length=FUTURE_DECISION_MAX_CHARS)


class FutureSelfResponse(BaseModel):
    conversation_id: str
    assistant_message_id: int | None
    message: str


@router.post(
    "/future-self",
    dependencies=[Depends(_verify_internal_caller)],
    responses={429: {"model": QuotaExceededResponse}},
)
async def future_self(
    req: FutureSelfRequest,
    user_id: Annotated[str, Depends(_require_user)],
) -> Any:
    supabase = await get_supabase()

    # §9.1.6: standard quota → chat-message bucket.
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

    run = await run_future_self(supabase, user_id=user_id, decision=req.decision)
    if run is None:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "future_self_failed")

    await increment_message_count(supabase, user_id)

    return FutureSelfResponse(
        conversation_id=run.conversation_id or "",
        assistant_message_id=run.assistant_message_id,
        message=run.message,
    )


# ----- Negotiation Sparring -------------------------------------------------


class NegotiationScenarioPayload(BaseModel):
    slug: str
    title: str
    blurb: str
    counterparty: str


class NegotiationScenariosResponse(BaseModel):
    scenarios: list[NegotiationScenarioPayload]


@router.get(
    "/negotiation-sparring/scenarios",
    dependencies=[Depends(_verify_internal_caller)],
    response_model=NegotiationScenariosResponse,
)
async def negotiation_scenarios() -> NegotiationScenariosResponse:
    """List the built-in scenarios. Cheap — used by the picker page."""

    return NegotiationScenariosResponse(
        scenarios=[
            NegotiationScenarioPayload(
                slug=s.slug,
                title=s.title,
                blurb=s.blurb,
                counterparty=s.counterparty,
            )
            for s in list_scenarios()
        ]
    )


class NegotiationStartRequest(BaseModel):
    scenario_slug: str = Field(min_length=1, max_length=80)


class NegotiationStartResponse(BaseModel):
    conversation_id: str
    scenario_slug: str
    scenario_title: str
    counterparty: str
    opening_line: str


@router.post(
    "/negotiation-sparring",
    dependencies=[Depends(_verify_internal_caller)],
)
async def negotiation_start(
    req: NegotiationStartRequest,
    user_id: Annotated[str, Depends(_require_user)],
) -> Any:
    supabase = await get_supabase()
    try:
        result = await start_session(
            supabase,
            user_id=user_id,
            scenario_slug=req.scenario_slug,
        )
    except UnknownScenarioError as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown_scenario") from err

    return NegotiationStartResponse(
        conversation_id=result.conversation_id,
        scenario_slug=result.scenario.slug,
        scenario_title=result.scenario.title,
        counterparty=result.scenario.counterparty,
        opening_line=result.scenario.opening_line,
    )


class NegotiationCritiqueRequest(BaseModel):
    conversation_id: str = Field(min_length=8, max_length=64)


class NegotiationCritiqueResponse(BaseModel):
    conversation_id: str
    scenario_slug: str
    scenario_title: str
    assistant_message_id: int | None
    strengths: list[str]
    weaknesses: list[str]
    alternative: str


@router.post(
    "/negotiation-sparring/critique",
    dependencies=[Depends(_verify_internal_caller)],
    responses={429: {"model": QuotaExceededResponse}},
)
async def negotiation_critique(
    req: NegotiationCritiqueRequest,
    user_id: Annotated[str, Depends(_require_user)],
) -> Any:
    supabase = await get_supabase()

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

    try:
        result = await run_critique(
            supabase,
            user_id=user_id,
            conversation_id=req.conversation_id,
        )
    except NotANegotiationError as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(err) or "not_a_negotiation") from err

    if result is None:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "critique_failed")

    await increment_message_count(supabase, user_id)

    return NegotiationCritiqueResponse(
        conversation_id=result.conversation_id,
        scenario_slug=result.scenario.slug,
        scenario_title=result.scenario.title,
        assistant_message_id=result.assistant_message_id,
        strengths=result.critique.strengths,
        weaknesses=result.critique.weaknesses,
        alternative=result.critique.alternative,
    )


# ----- Breakup Analyzer -----------------------------------------------------


class BreakupAnalyzerRequest(BaseModel):
    text_thread: str = Field(min_length=50, max_length=THREAD_MAX_CHARS)
    duration: str = Field(min_length=1, max_length=DURATION_MAX_CHARS)
    user_age: int = Field(ge=16, le=120)
    partner_age: int = Field(ge=16, le=120)
    intent: Annotated[str, Field(pattern="^(repair|end)$")]


class AttachmentDynamicsPayload(BaseModel):
    user: str
    partner: str
    summary: str


class SuggestedMessagePayload(BaseModel):
    intent: str
    text: str


class BreakupAnalyzerResponse(BaseModel):
    conversation_id: str
    assistant_message_id: int | None
    attachment_dynamics: AttachmentDynamicsPayload
    reconciliation_likelihood: str
    reconciliation_reasoning: str
    missing_things: list[str]
    suggested_message: SuggestedMessagePayload


@router.post(
    "/breakup-analyzer",
    dependencies=[Depends(_verify_internal_caller)],
    responses={429: {"model": QuotaExceededResponse}},
)
async def breakup_analyzer(
    req: BreakupAnalyzerRequest,
    user_id: Annotated[str, Depends(_require_user)],
) -> Any:
    supabase = await get_supabase()

    # §9.3.3: counts as 3 messages. Bail BEFORE the LLM call if the user
    # can't afford the full charge.
    quota = await get_message_quota(supabase, user_id)
    if quota.remaining < BREAKUP_QUOTA_COST:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "quota_exceeded",
                "tier": quota.tier,
                "limit": quota.limit,
                "used": quota.used,
                "reset_at": quota.reset_at.isoformat(),
                "upgrade_url": "/pricing",
                "cost": BREAKUP_QUOTA_COST,
            },
        )

    safety = await classify_message(
        req.text_thread,
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

    intent_literal: Any = req.intent  # narrowed by the regex on the field
    run = await run_breakup_analyzer(
        supabase,
        user_id=user_id,
        text_thread=req.text_thread,
        duration=req.duration,
        user_age=req.user_age,
        partner_age=req.partner_age,
        intent=intent_literal,
    )
    if run is None:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "breakup_analyzer_failed")

    await increment_message_count(supabase, user_id, count=BREAKUP_QUOTA_COST)

    return BreakupAnalyzerResponse(
        conversation_id=run.conversation_id or "",
        assistant_message_id=run.assistant_message_id,
        attachment_dynamics=AttachmentDynamicsPayload(
            user=run.result.attachment_dynamics.user,
            partner=run.result.attachment_dynamics.partner,
            summary=run.result.attachment_dynamics.summary,
        ),
        reconciliation_likelihood=run.result.reconciliation_likelihood,
        reconciliation_reasoning=run.result.reconciliation_reasoning,
        missing_things=run.result.missing_things,
        suggested_message=SuggestedMessagePayload(
            intent=run.result.suggested_message.intent,
            text=run.result.suggested_message.text,
        ),
    )
