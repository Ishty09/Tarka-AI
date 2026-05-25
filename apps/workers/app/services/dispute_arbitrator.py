"""Couple-dispute arbitrator.

When both partners have submitted their perspective on a fight, this
service calls quarrel-argue with a structured prompt and returns a
JSON verdict that both will see.

The verdict is opinionated on purpose (anti-sycophant rules apply —
no flattery, name who escalated first when clear, give separate
concrete advice to each partner). Confidence < 5 should be honest
when the info is one-sided.

Reply language matches the perspectives' language (Bangla in →
Bangla out), per the §7.3 rule #9 already on the system prompt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog

from app.services.langfuse_trace import build_metadata as build_trace_metadata
from app.services.llm import LiteLLMError, LiteLLMNetworkError, QUARREL_ARGUE, get_llm_client

log = structlog.get_logger(__name__)


ARBITRATION_SYSTEM_PROMPT = """You are an experienced couples therapist with anti-sycophant rules. Two partners are in conflict. Each submitted their side independently. Your job: synthesize both perspectives and produce a JSON verdict.

Rules:
1. Both partners will see this verdict. Be honest with both — never flatter.
2. Identify who escalated FIRST. Acknowledge that both usually contribute.
3. Distinguish what each was SAYING vs what they ACTUALLY wanted.
4. Spot patterns (this fight is about X but feels like Y).
5. Concrete next steps, separate per partner — actionable in 24 hours.
6. Confidence 0-10. Be honest when info is one-sided (low score).
7. Reply in the language the perspectives were written in. If they're in different languages, match Partner A.
8. Output ONLY valid JSON matching the schema. No prose around it.

JSON schema:
{
  "summary": string (1-2 sentences, neutral framing),
  "who_escalated_first": "a" | "b" | "both" | "unclear",
  "what_a_actually_wanted": string,
  "what_b_actually_wanted": string,
  "patterns_detected": [string, ...] (0-3 patterns),
  "advice_for_a": [string, string] (2 concrete steps),
  "advice_for_b": [string, string] (2 concrete steps),
  "what_to_do_next": string (1 concrete action both should take in 24h),
  "confidence": integer 0-10
}
"""


@dataclass(slots=True)
class ArbitrationResult:
    verdict: dict[str, Any]
    model: str
    raw_response: str


class ArbitrationError(Exception):
    """Arbitration call or parse failed. Caller stamps the row accordingly."""


async def arbitrate(
    *,
    perspective_a: str,
    perspective_b: str,
    couple_link_id: str,
    user_a_id: str,
) -> ArbitrationResult:
    """Call quarrel-argue with both perspectives, return parsed verdict.

    Raises ArbitrationError on LLM failure or JSON parse failure.
    """

    if not perspective_a.strip() or not perspective_b.strip():
        raise ArbitrationError("both perspectives required")

    user_message = (
        f"Partner A's perspective:\n{perspective_a.strip()}\n\n"
        f"Partner B's perspective:\n{perspective_b.strip()}"
    )

    client = get_llm_client()
    try:
        result = await client.chat(
            model=QUARREL_ARGUE,
            messages=[
                {"role": "system", "content": ARBITRATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_tokens=2000,
            response_format={"type": "json_object"},
            metadata=build_trace_metadata(
                name="dispute_arbitration",
                user_id=user_a_id,
                session_id=couple_link_id,
                extra={"couple_link_id": couple_link_id},
            ),
        )
    except (LiteLLMError, LiteLLMNetworkError) as err:
        raise ArbitrationError(f"llm call failed: {err}") from err

    try:
        raw = result["choices"][0]["message"]["content"]
        model_used = result.get("model", QUARREL_ARGUE)
    except (KeyError, IndexError) as err:
        raise ArbitrationError(f"unexpected llm response shape: {err}") from err

    try:
        verdict = json.loads(raw)
    except json.JSONDecodeError as err:
        raise ArbitrationError(f"verdict not valid json: {err}") from err

    # Light validation — keys we render in the UI must exist.
    for required in (
        "summary",
        "who_escalated_first",
        "what_a_actually_wanted",
        "what_b_actually_wanted",
        "advice_for_a",
        "advice_for_b",
        "what_to_do_next",
        "confidence",
    ):
        if required not in verdict:
            raise ArbitrationError(f"verdict missing key: {required}")

    return ArbitrationResult(
        verdict=verdict,
        model=model_used,
        raw_response=raw,
    )
