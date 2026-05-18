"""Content moderation service (CLAUDE.md §9.2.5, §10.2).

Single quarrel-cheap call returning approve / reject / flag. Used by the
roast-feed submission flow (step 32) and by persona-marketplace
moderation (§10.2 deferred). Failure mode: any defensive-deny path
returns 'flag' so a human can review — we never approve on uncertainty.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, Literal

import structlog
from pydantic import BaseModel, Field, ValidationError

from app.prompts.moderation import CONTENT_MODERATION_PROMPT
from app.services.llm import (
    QUARREL_CHEAP,
    LiteLLMClient,
    LiteLLMError,
    LiteLLMNetworkError,
    get_llm_client,
)

log = structlog.get_logger(__name__)


ModerationAction = Literal["approve", "reject", "flag"]
ModerationKind = Literal["roast_feed_post", "persona_system_prompt"]


class ModerationResult(BaseModel):
    action: ModerationAction
    reason: str = Field(min_length=1, max_length=500)
    categories: list[str] = Field(default_factory=list, max_length=10)


# Default verdict when the classifier itself fails. We don't approve on
# uncertainty — a flagged item lands in the admin queue where a human
# can decide. Reject would be too harsh; approve would leak content
# during outages.
_DEFENSIVE_FLAG = ModerationResult(
    action="flag",
    reason="moderator_call_failed",
    categories=["moderator_failure"],
)


async def moderate(
    *,
    content: str,
    kind: ModerationKind,
    client: LiteLLMClient | None = None,
    user_id: str | None = None,
) -> ModerationResult:
    """Classify content. Returns _DEFENSIVE_FLAG on any failure path."""

    if not content.strip():
        return ModerationResult(
            action="reject",
            reason="empty_content",
            categories=["empty"],
        )

    llm = client or get_llm_client()
    body = f"<kind>{kind}</kind>\n<content>\n{content}\n</content>"

    try:
        response = await llm.chat(
            model=QUARREL_CHEAP,
            messages=[
                {"role": "system", "content": CONTENT_MODERATION_PROMPT},
                {"role": "user", "content": body},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            user=user_id,
            metadata={
                "generation_name": "moderation",
                "trace_user_id": user_id,
                "tags": ["moderation", kind],
            },
        )
    except (LiteLLMError, LiteLLMNetworkError) as err:
        log.warning("moderation.llm_error", kind=kind, error=str(err))
        return _DEFENSIVE_FLAG

    try:
        raw = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        return _DEFENSIVE_FLAG
    if isinstance(raw, list):
        raw = "".join(
            block.get("text", "")
            for block in raw
            if isinstance(block, dict) and block.get("type") == "text"
        )
    if not isinstance(raw, str):
        return _DEFENSIVE_FLAG

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("moderation.json_decode_failed", raw=raw[:200])
        return _DEFENSIVE_FLAG
    try:
        return ModerationResult.model_validate(parsed)
    except ValidationError as err:
        log.warning("moderation.schema_invalid", error=str(err))
        return _DEFENSIVE_FLAG


__all__ = [
    "ModerationAction",
    "ModerationKind",
    "ModerationResult",
    "moderate",
]
