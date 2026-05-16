"""User-facts retrieval stub.

Phase C steps 13-15 (CLAUDE.md §27) will replace this with real semantic
retrieval from `user_facts` and `contradictions`. Until then we return an
empty bundle so the chat assembly code is already wired to a stable shape.
"""

from __future__ import annotations

from dataclasses import dataclass

from supabase import AsyncClient


@dataclass(slots=True)
class UserFactsBundle:
    """Serialized facts + contradictions block injected into the system message.

    `text` is what the model sees. `count` is exposed for telemetry — we want
    to alert if it falls to zero for active users (Phase C wiring).
    """

    text: str
    count: int


async def load_user_facts(
    supabase: AsyncClient,  # noqa: ARG001 — unused until Phase C
    user_id: str,  # noqa: ARG001
    *,
    query_message: str,  # noqa: ARG001
    limit: int = 10,  # noqa: ARG001
) -> UserFactsBundle:
    """Phase C placeholder. Returns an empty bundle.

    Once embeddings + pgvector retrieval are wired in step 14-15, this
    function will run a vector search on user_facts.embedding, filter
    contradictions, and produce the §7.3 <user_facts> XML block.
    """

    return UserFactsBundle(text="", count=0)
