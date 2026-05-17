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

from dataclasses import dataclass

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
    """

    text: str
    count: int


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
        return UserFactsBundle(text="", count=0)

    lines = [_format_fact(row) for row in matches]
    return UserFactsBundle(text="\n".join(lines), count=len(matches))


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
