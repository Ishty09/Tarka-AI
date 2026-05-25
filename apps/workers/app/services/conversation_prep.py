"""Pre-conversation coaching for one partner in a couple.

PRIVATE to the requesting partner. Generates a structured prep brief
they can review before a hard talk:
  - their talking points (3 specific anchors)
  - likely things the partner will say + what each actually means
  - de-escalation paths to use when it gets heated
  - one concrete opening line

Privacy: row owned solely by the user. Partner cannot read it (RLS
in 20260526120400_couple_conversation_preps.sql).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog

from app.services.langfuse_trace import build_metadata as build_trace_metadata
from app.services.llm import LiteLLMError, LiteLLMNetworkError, QUARREL_ARGUE, get_llm_client

log = structlog.get_logger(__name__)


PREP_SYSTEM_PROMPT = """You are a couples therapist briefing ONE partner before a hard conversation. This is private — the other partner won't see it.

Anti-sycophant rules apply. Don't flatter the user. Name where they're being weak or self-serving.

Output ONLY valid JSON matching this schema. Match the language of the inputs.

{
  "talking_points": [string, string, string]   // 3 specific anchors for the user
  "partner_might_say": [                       // 3 likely things the partner says
    { "statement": string, "actually_means": string }
  ]
  "deescalation_paths": [string, string]       // 2 things to do when it heats up
  "opening_line": string                       // ONE concrete sentence to start with
  "watch_out_for": string                      // honest call-out — where the user is being defensive/avoidant/manipulative
}

Rules:
1. Talking points must be SPECIFIC to the topic + desired outcome. No platitudes.
2. partner_might_say should anticipate the partner's strongest moves, not strawmen.
3. opening_line should be 1-2 sentences max — actually say-able out loud.
4. watch_out_for is the anti-sycophant beat. Tell the user what they're not admitting.
"""


@dataclass(slots=True)
class PrepResult:
    prep: dict[str, Any]
    model: str


class PrepError(Exception):
    pass


async def generate_prep(
    *,
    user_id: str,
    couple_link_id: str,
    topic: str,
    desired_outcome: str | None,
    context: str | None,
    partner_known_facts: list[str] | None = None,
) -> PrepResult:
    """Run quarrel-argue to produce a JSON prep brief."""

    if not topic.strip():
        raise PrepError("topic required")

    user_payload: list[str] = [f"Topic: {topic.strip()}"]
    if desired_outcome:
        user_payload.append(f"Desired outcome: {desired_outcome.strip()}")
    if context:
        user_payload.append(f"Context (private to me, partner won't see):\n{context.strip()}")
    if partner_known_facts:
        user_payload.append(
            "What we know about the partner (from past interactions):\n- "
            + "\n- ".join(partner_known_facts)
        )

    client = get_llm_client()
    try:
        result = await client.chat(
            model=QUARREL_ARGUE,
            messages=[
                {"role": "system", "content": PREP_SYSTEM_PROMPT},
                {"role": "user", "content": "\n\n".join(user_payload)},
            ],
            max_tokens=2000,
            response_format={"type": "json_object"},
            metadata=build_trace_metadata(
                name="conversation_prep",
                user_id=user_id,
                session_id=couple_link_id,
            ),
        )
    except (LiteLLMError, LiteLLMNetworkError) as err:
        raise PrepError(f"llm call failed: {err}") from err

    try:
        raw = result["choices"][0]["message"]["content"]
        model_used = result.get("model", QUARREL_ARGUE)
    except (KeyError, IndexError) as err:
        raise PrepError(f"unexpected response: {err}") from err

    try:
        prep = json.loads(raw)
    except json.JSONDecodeError as err:
        raise PrepError(f"not valid json: {err}") from err

    for required in (
        "talking_points",
        "partner_might_say",
        "deescalation_paths",
        "opening_line",
        "watch_out_for",
    ):
        if required not in prep:
            raise PrepError(f"missing key: {required}")

    return PrepResult(prep=prep, model=model_used)
