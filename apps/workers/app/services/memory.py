"""User-facts retrieval via pgvector cosine similarity.

Called by the chat route on every turn to assemble the §7.3 <user_facts>
block injected into the system prompt. Embedding cost is one extra
quarrel-embed call per turn; the §7.6 caching strategy targets 70%+
input-token cache hit, but the user_facts block itself rotates by query
so it sits outside the long-lived cache window.

Failure modes:
    - LLM embed error          -> empty bundle (no facts injected, no raise)
    - RPC error                -> empty bundle
    - Zero matches             -> empty bundle

In every case the chat turn still goes through; the persona just lacks
memory for that one response.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from supabase import AsyncClient

from app.services._db_typing import rows as _rows
from app.services.llm import (
    QUARREL_EMBED,
    LiteLLMClient,
    LiteLLMError,
    LiteLLMNetworkError,
    get_llm_client,
)

log = structlog.get_logger(__name__)


@dataclass(slots=True)
class UserFactsBundle:
    """Serialized facts block injected into the system message.

    `text` is what the model sees. `count` is exposed for telemetry.
    `fact_ids` lets downstream callers (contradiction lookup) avoid re-
    embedding the query just to find matching rows.
    """

    text: str
    count: int
    fact_ids: list[int] = field(default_factory=list)


@dataclass(slots=True)
class ContradictionCallout:
    """One unsurfaced contradiction worth flagging to the user this turn.

    Mirrors the rows the chat-stream SSE event carries to the client.
    """

    id: int
    severity: int
    summary: str
    fact_a_text: str
    fact_a_created_at: str
    fact_b_text: str
    fact_b_created_at: str


async def load_user_facts(
    supabase: AsyncClient,
    user_id: str,
    *,
    query_message: str,
    limit: int = 10,
    min_similarity: float = 0.3,
    client: LiteLLMClient | None = None,
) -> UserFactsBundle:
    """Top-K user_facts ranked by cosine similarity to query_message.

    Calls the `match_user_facts` Postgres function (added in migration
    20260518120000) which uses the hnsw cosine index on
    user_facts.embedding.
    """

    if not query_message.strip():
        return UserFactsBundle(text="", count=0)

    llm = client or get_llm_client()

    try:
        vectors = await llm.embed(
            model=QUARREL_EMBED,
            input=query_message,
            user=user_id,
        )
    except (LiteLLMError, LiteLLMNetworkError) as err:
        log.warning("memory.embed.failed", user_id=user_id, error=str(err))
        return UserFactsBundle(text="", count=0)

    if not vectors:
        return UserFactsBundle(text="", count=0)
    query_embedding = vectors[0]

    try:
        res = await supabase.rpc(
            "match_user_facts",
            {
                "p_user_id": user_id,
                "p_query_embedding": query_embedding,
                "p_match_count": limit,
                "p_min_similarity": min_similarity,
            },
        ).execute()
    except Exception as err:  # noqa: BLE001 — best-effort path
        log.warning("memory.rpc.failed", user_id=user_id, error=str(err))
        return UserFactsBundle(text="", count=0)

    matches = _rows(res.data)
    if not matches:
        return UserFactsBundle(text="", count=0, fact_ids=[])

    lines = [_format_fact(row) for row in matches]
    fact_ids = [int(row["id"]) for row in matches if "id" in row]
    return UserFactsBundle(text="\n".join(lines), count=len(matches), fact_ids=fact_ids)


async def find_relevant_contradiction(
    supabase: AsyncClient,
    user_id: str,
    *,
    fact_ids: list[int],
    min_severity: int = 5,
) -> ContradictionCallout | None:
    """Pick the most severe unsurfaced contradiction touching `fact_ids`.

    "Unsurfaced" = surfaced_at IS NULL AND dismissed_at IS NULL. The
    contradiction is matched if either fact_a_id or fact_b_id appears in
    `fact_ids` (the facts the chat turn just retrieved as relevant).
    Returns None on no match or any error — callouts are best-effort.
    """

    if not fact_ids:
        return None

    # supabase-py exposes the postgrest .or_() filter for compound clauses.
    # Format: fact_a_id.in.(1,2,3),fact_b_id.in.(1,2,3)
    ids_csv = ",".join(str(i) for i in fact_ids)
    or_clause = f"fact_a_id.in.({ids_csv}),fact_b_id.in.({ids_csv})"

    try:
        res = (
            await supabase.table("contradictions")
            .select(
                "id, severity, summary, surfaced_at, dismissed_at, "
                "fact_a:fact_a_id (id, fact, created_at), "
                "fact_b:fact_b_id (id, fact, created_at)",
            )
            .eq("user_id", user_id)
            .is_("surfaced_at", "null")
            .is_("dismissed_at", "null")
            .gte("severity", min_severity)
            .or_(or_clause)
            .order("severity", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as err:  # noqa: BLE001 — best-effort path
        log.warning(
            "memory.contradiction_lookup.failed",
            user_id=user_id,
            error=str(err),
        )
        return None

    rows = _rows(res.data)
    if not rows:
        return None

    row = rows[0]
    fact_a = _unwrap_fact(row.get("fact_a"))
    fact_b = _unwrap_fact(row.get("fact_b"))
    if not fact_a or not fact_b:
        # If the join didn't resolve we can't render a callout — skip.
        return None

    return ContradictionCallout(
        id=int(row["id"]),
        severity=int(row["severity"]),
        summary=str(row["summary"]),
        fact_a_text=str(fact_a.get("fact", "")),
        fact_a_created_at=str(fact_a.get("created_at", "")),
        fact_b_text=str(fact_b.get("fact", "")),
        fact_b_created_at=str(fact_b.get("created_at", "")),
    )


async def mark_contradiction_surfaced(
    supabase: AsyncClient, contradiction_id: int
) -> None:
    """Stamp surfaced_at so we don't show the same callout every turn."""

    try:
        await (
            supabase.table("contradictions")
            .update({"surfaced_at": datetime.now(UTC).isoformat()})
            .eq("id", contradiction_id)
            .execute()
        )
    except Exception as err:  # noqa: BLE001 — best-effort
        log.warning(
            "memory.contradiction_mark.failed",
            contradiction_id=contradiction_id,
            error=str(err),
        )


def _unwrap_fact(value: Any) -> dict[str, Any] | None:
    """Embedded foreign-key selects can return either a dict or a list of dicts."""

    if value is None:
        return None
    if isinstance(value, list):
        return value[0] if value else None
    if isinstance(value, dict):
        return value
    return None


def _format_fact(row: dict[str, object]) -> str:
    """Render one fact for the <user_facts> XML block.

    Format: `- [category] fact text  (since YYYY-MM-DD, conf=0.85)`
    Kept terse so 10 facts comfortably fit in a single cache slot.
    """

    category = row.get("category") or "uncategorized"
    fact = row.get("fact") or ""
    confidence = row.get("confidence")
    created = row.get("created_at")
    created_str = str(created)[:10] if created else "?"
    confidence_str = (
        f"conf={float(confidence):.2f}"  # type: ignore[arg-type]
        if confidence is not None
        else "conf=?"
    )
    return f"- [{category}] {fact}  (since {created_str}, {confidence_str})"
