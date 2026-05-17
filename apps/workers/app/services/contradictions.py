"""Contradiction detection service (CLAUDE.md §9.4.1).

Compares pairs of user_facts via LLM and persists rows into
contradictions when severity meets the threshold. Designed to be called
from jobs/contradiction_batch.py for nightly runs, but also exposed for
ad-hoc invocation (admin trigger, tests).

Pair selection uses pgvector top-K so we LLM-judge only the most-likely
candidates instead of the full N×M product. Without that filter the
nightly bill grows quadratically as a user accumulates facts.

Failure modes follow the same pattern as services/safety.py and
fact_extraction.py — every LLM, parse, or DB error is logged and
swallowed; the batch keeps going. A flaky upstream must not kill the
entire run.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any

import structlog
from pydantic import BaseModel, Field, ValidationError
from supabase import AsyncClient

from app.prompts.contradiction import CONTRADICTION_JUDGE_PROMPT
from app.services._db_typing import rows as _rows
from app.services.llm import (
    QUARREL_ARGUE,
    LiteLLMClient,
    LiteLLMError,
    LiteLLMNetworkError,
    get_llm_client,
)
from app.services.supabase_client import get_supabase

log = structlog.get_logger(__name__)


# §6.2 CHECK constraint range for contradictions.severity.
MIN_SEVERITY = 0
MAX_SEVERITY = 10

# Severity at or above which we insert a contradiction row. Lower scores
# are "not really a contradiction" or below the noise floor.
DEFAULT_SEVERITY_THRESHOLD = 5

# Safety caps per run. Without these a single user with 1000 facts could
# trigger 1000s of LLM calls per nightly batch.
DEFAULT_MAX_CANDIDATES_PER_FACT = 5
DEFAULT_MAX_PAIRS_PER_USER = 100


class ContradictionJudgment(BaseModel):
    """Parsed LLM verdict for one pair."""

    is_contradiction: bool
    severity: Annotated[int, Field(ge=MIN_SEVERITY, le=MAX_SEVERITY)]
    summary: str


# ----- LLM call --------------------------------------------------------------


async def judge_pair(
    fact_a_text: str,
    fact_b_text: str,
    *,
    client: LiteLLMClient | None = None,
) -> ContradictionJudgment | None:
    """Single LLM call. Returns None on any failure (caller skips the pair)."""

    llm = client or get_llm_client()
    user_payload = f"<fact_a>{fact_a_text}</fact_a>\n<fact_b>{fact_b_text}</fact_b>"

    try:
        response = await llm.chat(
            model=QUARREL_ARGUE,
            messages=[
                {"role": "system", "content": CONTRADICTION_JUDGE_PROMPT},
                {"role": "user", "content": user_payload},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            metadata={
                "generation_name": "contradiction_judge",
                "tags": ["contradiction_judge"],
            },
        )
    except (LiteLLMError, LiteLLMNetworkError) as err:
        log.warning("contradictions.judge.llm_error", error=str(err))
        return None

    try:
        raw = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        return None

    if isinstance(raw, list):
        raw = "".join(
            block.get("text", "")
            for block in raw
            if isinstance(block, dict) and block.get("type") == "text"
        )
    if not isinstance(raw, str):
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("contradictions.judge.json_decode_failed", raw=raw[:200])
        return None
    try:
        return ContradictionJudgment.model_validate(parsed)
    except ValidationError as err:
        log.warning("contradictions.judge.schema_invalid", error=str(err))
        return None


# ----- DB helpers ------------------------------------------------------------


async def fetch_new_embedded_facts(
    supabase: AsyncClient,
    user_id: str,
    *,
    since: datetime,
) -> list[dict[str, Any]]:
    """Facts created after `since` that already have an embedding.

    Facts without embeddings can't be candidate-paired via pgvector, so we
    skip them and let the next run pick them up once embed_facts has caught
    up.
    """

    res = (
        await supabase.table("user_facts")
        .select("id, fact, embedding")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .gte("created_at", since.isoformat())
        .not_.is_("embedding", "null")
        .execute()
    )
    return _rows(res.data)


async def find_candidate_pairs(
    supabase: AsyncClient,
    user_id: str,
    new_fact: dict[str, Any],
    *,
    limit: int = DEFAULT_MAX_CANDIDATES_PER_FACT,
    min_similarity: float = 0.5,
) -> list[dict[str, Any]]:
    """Top-K other facts most similar to new_fact.

    Calls match_user_facts (Phase C step 14 migration). Excludes new_fact
    itself client-side because the SQL function doesn't accept an
    exclude_id parameter (additive RPC, we don't want to mutate the
    signature yet).
    """

    embedding = new_fact.get("embedding")
    if not embedding:
        return []

    res = await supabase.rpc(
        "match_user_facts",
        {
            "p_user_id": user_id,
            "p_query_embedding": embedding,
            # +1 so removing self still leaves up to `limit` candidates.
            "p_match_count": limit + 1,
            "p_min_similarity": min_similarity,
        },
    ).execute()

    matches = _rows(res.data)
    return [m for m in matches if m.get("id") != new_fact["id"]][:limit]


async def insert_contradiction(
    supabase: AsyncClient,
    *,
    user_id: str,
    fact_a_id: int,
    fact_b_id: int,
    severity: int,
    summary: str,
) -> bool:
    """Insert a contradiction row with canonical pair ordering.

    Returns True if a new row was created, False if it already existed
    (unique constraint on (user_id, fact_a_id, fact_b_id)).
    """

    a_id, b_id = sorted([fact_a_id, fact_b_id])
    payload: dict[str, Any] = {
        "user_id": user_id,
        "fact_a_id": a_id,
        "fact_b_id": b_id,
        "severity": severity,
        "summary": summary,
    }
    try:
        res = (
            await supabase.table("contradictions")
            .upsert(payload, on_conflict="user_id,fact_a_id,fact_b_id", ignore_duplicates=True)
            .execute()
        )
    except Exception as err:  # noqa: BLE001 — best-effort path
        log.warning(
            "contradictions.insert.failed",
            user_id=user_id,
            a=a_id,
            b=b_id,
            error=str(err),
        )
        return False
    return bool(_rows(res.data))


# ----- Orchestration ---------------------------------------------------------


async def run_for_user(
    supabase: AsyncClient,
    *,
    user_id: str,
    since: datetime,
    client: LiteLLMClient | None = None,
    severity_threshold: int = DEFAULT_SEVERITY_THRESHOLD,
    max_pairs: int = DEFAULT_MAX_PAIRS_PER_USER,
) -> dict[str, int]:
    """Process all new facts for one user. Returns counts for telemetry."""

    new_facts = await fetch_new_embedded_facts(supabase, user_id, since=since)
    pairs_judged = 0
    contradictions_inserted = 0
    pairs_skipped = 0

    for new_fact in new_facts:
        if pairs_judged >= max_pairs:
            log.info(
                "contradictions.user.cap_reached",
                user_id=user_id,
                max_pairs=max_pairs,
            )
            break

        candidates = await find_candidate_pairs(supabase, user_id, new_fact)
        for candidate in candidates:
            if pairs_judged >= max_pairs:
                break
            pairs_judged += 1

            verdict = await judge_pair(new_fact["fact"], candidate["fact"], client=client)
            if verdict is None or not verdict.is_contradiction:
                pairs_skipped += 1
                continue
            if verdict.severity < severity_threshold:
                pairs_skipped += 1
                continue

            inserted = await insert_contradiction(
                supabase,
                user_id=user_id,
                fact_a_id=int(new_fact["id"]),
                fact_b_id=int(candidate["id"]),
                severity=verdict.severity,
                summary=verdict.summary,
            )
            if inserted:
                contradictions_inserted += 1

    log.info(
        "contradictions.user.done",
        user_id=user_id,
        new_facts=len(new_facts),
        pairs_judged=pairs_judged,
        pairs_skipped=pairs_skipped,
        contradictions_inserted=contradictions_inserted,
    )
    return {
        "new_facts": len(new_facts),
        "pairs_judged": pairs_judged,
        "contradictions_inserted": contradictions_inserted,
    }


async def find_users_with_new_facts(
    supabase: AsyncClient, *, since: datetime
) -> list[str]:
    """Distinct user_ids that inserted at least one fact since `since`."""

    res = (
        await supabase.table("user_facts")
        .select("user_id")
        .gte("created_at", since.isoformat())
        .execute()
    )
    return list({str(row["user_id"]) for row in _rows(res.data)})


async def run_batch(
    *,
    since: datetime,
    client: LiteLLMClient | None = None,
    supabase: AsyncClient | None = None,
) -> dict[str, int]:
    """Top-level entry point used by jobs and the cron route."""

    sb = supabase or await get_supabase()
    users = await find_users_with_new_facts(sb, since=since)

    totals = {"users": len(users), "contradictions_inserted": 0, "pairs_judged": 0}
    for user_id in users:
        result = await run_for_user(sb, user_id=user_id, since=since, client=client)
        totals["contradictions_inserted"] += result["contradictions_inserted"]
        totals["pairs_judged"] += result["pairs_judged"]

    log.info("contradictions.batch.done", **totals)
    return totals


__all__ = [
    "ContradictionJudgment",
    "DEFAULT_MAX_CANDIDATES_PER_FACT",
    "DEFAULT_MAX_PAIRS_PER_USER",
    "DEFAULT_SEVERITY_THRESHOLD",
    "fetch_new_embedded_facts",
    "find_candidate_pairs",
    "find_users_with_new_facts",
    "insert_contradiction",
    "judge_pair",
    "run_batch",
    "run_for_user",
]
