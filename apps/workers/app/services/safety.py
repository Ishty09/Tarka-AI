"""Safety screen + PII redaction service.

Public surface:
    - SafetyResult        : pydantic model returned by classify_message
    - classify_message    : LLM-backed safety verdict (defensive-deny on failure)
    - redact              : produce redacted text from offsets

CLAUDE.md anchors:
    §1.5  every inbound user message hits the safety screen first
    §1.12 redact PII before persistence; embeddings run on the redacted version
    §7.5  prompt + JSON shape
    §7.2  routes through quarrel-cheap (the classification tier)
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

import structlog
from pydantic import BaseModel, Field, ValidationError

from app.prompts.safety_screen import SAFETY_SCREEN_PROMPT
from app.services.llm import (
    QUARREL_CHEAP,
    LiteLLMClient,
    LiteLLMError,
    LiteLLMNetworkError,
    get_llm_client,
)

log = structlog.get_logger(__name__)

# Verdict the LLM can return — matches packages/shared schemas/llm/safety_screen.ts.
LlmVerdict = Literal[
    "safe",
    "crisis",
    "abuse",
    "minor_self_sexualization",
    "jailbreak",
]

# Verdict we may STAMP after defensive redaction (extends LlmVerdict).
StampedVerdict = Literal[
    "safe",
    "crisis",
    "abuse",
    "minor_self_sexualization",
    "jailbreak",
    "redacted",
]

PiiCategory = Literal["phone", "email", "address", "id", "cc"]


class Redaction(BaseModel):
    """A single PII span. Offsets are inclusive-start, exclusive-end (str slice)."""

    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(ge=0)]
    category: PiiCategory


class SafetyResult(BaseModel):
    """Parsed §7.5 classifier output."""

    verdict: LlmVerdict
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    reason: str
    redactions: list[Redaction] = Field(default_factory=list)


# Defensive-deny fallback used when the LLM call fails or returns garbage.
# We do NOT default to "safe" — that would let malformed responses bypass the
# screen entirely. We treat it as a jailbreak so the route refuses the turn
# and the caller can decide whether to retry.
_DEFENSIVE_DENY = SafetyResult(
    verdict="jailbreak",
    confidence=1.0,
    reason="defensive_deny: safety classifier failed; refusing turn",
    redactions=[],
)


async def classify_message(
    user_message: str,
    *,
    user_id: str | None = None,
    conversation_id: str | None = None,
    client: LiteLLMClient | None = None,
) -> SafetyResult:
    """Run the §7.5 classifier on a single user message.

    Returns SafetyResult — verdict is `jailbreak` if the call or parse failed,
    so the caller's `verdict == "safe"` check is the only gate they need.
    """

    if not user_message.strip():
        # Empty input can't be unsafe — but also shouldn't reach the model.
        return SafetyResult(verdict="safe", confidence=1.0, reason="empty_input")

    llm = client or get_llm_client()

    messages = [
        {"role": "system", "content": SAFETY_SCREEN_PROMPT},
        {"role": "user", "content": user_message},
    ]

    try:
        response = await llm.chat(
            model=QUARREL_CHEAP,
            messages=messages,
            temperature=0.0,
            response_format={"type": "json_object"},
            user=user_id,
            metadata={
                "generation_name": "safety_screen",
                "trace_user_id": user_id,
                "session_id": conversation_id,
                "tags": ["safety_screen"],
            },
        )
    except (LiteLLMError, LiteLLMNetworkError) as err:
        log.warning(
            "safety.classify.llm_error",
            user_id=user_id,
            conversation_id=conversation_id,
            error=str(err),
        )
        return _DEFENSIVE_DENY

    try:
        raw_content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as err:
        log.warning("safety.classify.malformed_response", error=str(err))
        return _DEFENSIVE_DENY

    if isinstance(raw_content, list):
        # Anthropic content-block list — concatenate text blocks.
        raw_content = "".join(
            block.get("text", "")
            for block in raw_content
            if isinstance(block, dict) and block.get("type") == "text"
        )

    if not isinstance(raw_content, str):
        log.warning("safety.classify.non_string_content")
        return _DEFENSIVE_DENY

    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError:
        log.warning("safety.classify.json_decode_failed", raw=raw_content[:200])
        return _DEFENSIVE_DENY

    try:
        return SafetyResult.model_validate(parsed)
    except ValidationError as err:
        log.warning("safety.classify.schema_invalid", error=str(err))
        return _DEFENSIVE_DENY


def redact(text: str, redactions: list[Redaction], *, marker: str = "[REDACTED]") -> str:
    """Apply offset-based redactions to a string.

    Out-of-range or overlapping spans are skipped defensively rather than
    raising — the classifier sometimes hallucinates offsets, and we'd rather
    persist a slightly under-redacted string than reject the whole turn.
    """

    if not redactions:
        return text

    # Sort by start ascending, then end descending so overlaps prefer the
    # longer span.
    spans = sorted(redactions, key=lambda r: (r.start, -r.end))
    out: list[str] = []
    cursor = 0
    length = len(text)
    for span in spans:
        if span.start < cursor or span.start >= length or span.end > length or span.end <= span.start:
            continue
        out.append(text[cursor : span.start])
        out.append(marker)
        cursor = span.end
    out.append(text[cursor:])
    return "".join(out)


__all__ = [
    "PiiCategory",
    "Redaction",
    "SafetyResult",
    "StampedVerdict",
    "classify_message",
    "redact",
]
