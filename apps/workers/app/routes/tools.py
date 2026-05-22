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
from app.services import analytics
from app.services.breakup_analyzer import (
    DURATION_MAX_CHARS,
    THREAD_MAX_CHARS,
    run_breakup_analyzer,
)
from app.services.breakup_analyzer import (
    QUOTA_COST as BREAKUP_QUOTA_COST,
)
from app.services.cope_detector import RATIONALIZATION_MAX_CHARS, run_cope_detector
from app.services.council import CouncilWipeoutError, run_council
from app.services.couples import (
    CoupleLinkNotActiveError,
    CoupleLinkNotFoundError,
    NotALinkMemberError,
    start_couple_session,
)
from app.services.decision_killer import DECISION_MAX_CHARS, run_decision_killer
from app.services.enforcement import (
    assert_not_suspended,
    check_quota,
    enforce_user,
    quota_detail,
)
from app.services.future_self import FUTURE_DECISION_MAX_CHARS, run_future_self
from app.services.groups import (
    GroupArchivedError,
    GroupNotFoundError,
    NotAGroupMemberError,
    start_group_session,
)
from app.services.moderation import ModerationKind, moderate
from app.services.negotiation import (
    NotANegotiationError,
    UnknownScenarioError,
    list_scenarios,
    run_critique,
    start_session,
)
from app.services.past_self import PAST_CONTENT_MAX_CHARS, run_past_self
from app.services.quotas import increment_council_count, increment_message_count
from app.services.roast_my_x import (
    CONTENT_MAX_CHARS as ROAST_CONTENT_MAX_CHARS,
)
from app.services.roast_my_x import (
    UnknownTargetError,
    is_known_target,
    run_roast_my_x,
)
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
    # Suspension + per-scope quota in one call (§50). Raises 403 / 429.
    await enforce_user(supabase, user_id=user_id, scope="council")

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
    await analytics.track_server("council_run", user_id=user_id)

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
    await enforce_user(supabase, user_id=user_id, scope="messages")

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
    await analytics.track_server("steelman_used", user_id=user_id)

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
    await enforce_user(supabase, user_id=user_id, scope="messages")

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
    await analytics.track_server("decision_killer_used", user_id=user_id)

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
    await enforce_user(supabase, user_id=user_id, scope="messages")

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
    await analytics.track_server("cope_detector_used", user_id=user_id)

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
    await enforce_user(supabase, user_id=user_id, scope="messages")

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
    await enforce_user(supabase, user_id=user_id, scope="messages")

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

    await analytics.track_server(
        "negotiation_sparring_started",
        user_id=user_id,
        data={"scenario_slug": result.scenario.slug},
    )

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

    await enforce_user(supabase, user_id=user_id, scope="messages")

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
    await assert_not_suspended(supabase, user_id=user_id)
    quota = await check_quota(supabase, user_id=user_id, scope="messages")
    if quota.remaining < BREAKUP_QUOTA_COST:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={**quota_detail(quota), "cost": BREAKUP_QUOTA_COST},
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
    await analytics.track_server("breakup_analyzer_used", user_id=user_id)

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


# ----- Roast My X -----------------------------------------------------------


class RoastMyXRequest(BaseModel):
    target: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=20, max_length=ROAST_CONTENT_MAX_CHARS)


class RoastMyXResponse(BaseModel):
    conversation_id: str
    assistant_message_id: int | None
    target: str
    roast: str


@router.post(
    "/roast-my-x",
    dependencies=[Depends(_verify_internal_caller)],
    responses={429: {"model": QuotaExceededResponse}},
)
async def roast_my_x(
    req: RoastMyXRequest,
    user_id: Annotated[str, Depends(_require_user)],
) -> Any:
    supabase = await get_supabase()

    if not is_known_target(req.target):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown_roast_target")

    # §9.2.2: counts as 1 message.
    await enforce_user(supabase, user_id=user_id, scope="messages")

    safety = await classify_message(
        req.content,
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
        run = await run_roast_my_x(
            supabase,
            user_id=user_id,
            target=req.target,
            content=req.content,
        )
    except UnknownTargetError as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown_roast_target") from err

    if run is None:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "roast_my_x_failed")

    await increment_message_count(supabase, user_id)

    return RoastMyXResponse(
        conversation_id=run.conversation_id or "",
        assistant_message_id=run.assistant_message_id,
        target=run.target,
        roast=run.roast,
    )


# ----- Moderation -----------------------------------------------------------


class ModerationRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    kind: ModerationKind


class ModerationResponse(BaseModel):
    action: str
    reason: str
    categories: list[str]


@router.post(
    "/moderate",
    dependencies=[Depends(_verify_internal_caller)],
    response_model=ModerationResponse,
)
async def moderate_content(
    req: ModerationRequest,
    user_id: Annotated[str, Depends(_require_user)],
) -> ModerationResponse:
    """Generic auto-moderation. Called by /api/feed/submit (§9.2.5) and by
    persona-marketplace submission (§10.2 deferred). Does NOT cost quota
    because the user is paying through the parent action.
    """

    result = await moderate(
        content=req.content,
        kind=req.kind,
        user_id=user_id,
    )
    return ModerationResponse(
        action=result.action,
        reason=result.reason,
        categories=result.categories,
    )


# ----- Couples shared chat --------------------------------------------------


class CoupleStartRequest(BaseModel):
    link_id: str = Field(min_length=8, max_length=64)


class CoupleStartResponse(BaseModel):
    link_id: str
    conversation_id: str
    user_a: str
    user_b: str


@router.post(
    "/couples/start",
    dependencies=[Depends(_verify_internal_caller)],
    response_model=CoupleStartResponse,
)
async def couples_start(
    req: CoupleStartRequest,
    user_id: Annotated[str, Depends(_require_user)],
) -> CoupleStartResponse:
    """Find or create the shared conversation for an active couple link
    (§9.3.1). Idempotent — repeat calls return the same conversation_id.
    """

    supabase = await get_supabase()
    try:
        session = await start_couple_session(
            supabase,
            user_id=user_id,
            link_id=req.link_id,
        )
    except CoupleLinkNotFoundError as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "couple_link_not_found") from err
    except NotALinkMemberError as err:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not_a_link_member") from err
    except CoupleLinkNotActiveError as err:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"couple_link_not_active:{err}",
        ) from err

    return CoupleStartResponse(
        link_id=session.link_id,
        conversation_id=session.conversation_id,
        user_a=session.user_a,
        user_b=session.user_b,
    )


# ----- Group rooms (§9.3.4) -------------------------------------------------


class GroupStartRequest(BaseModel):
    group_id: str = Field(min_length=8, max_length=64)


class GroupStartResponse(BaseModel):
    group_id: str
    conversation_id: str
    mediator_persona_id: str
    member_ids: list[str]


@router.post(
    "/groups/start",
    dependencies=[Depends(_verify_internal_caller)],
    response_model=GroupStartResponse,
)
async def groups_start(
    req: GroupStartRequest,
    user_id: Annotated[str, Depends(_require_user)],
) -> GroupStartResponse:
    """Find or create the shared conversation for an active group room.

    Idempotent — repeat calls return the same conversation_id.
    """

    supabase = await get_supabase()
    try:
        session = await start_group_session(
            supabase,
            user_id=user_id,
            group_id=req.group_id,
        )
    except GroupNotFoundError as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "group_not_found") from err
    except GroupArchivedError as err:
        raise HTTPException(status.HTTP_409_CONFLICT, "group_archived") from err
    except NotAGroupMemberError as err:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not_a_group_member") from err

    return GroupStartResponse(
        group_id=session.group_id,
        conversation_id=session.conversation_id,
        mediator_persona_id=session.mediator_persona_id,
        member_ids=session.member_ids,
    )
