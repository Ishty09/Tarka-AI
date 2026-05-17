"""Per-turn fact extraction.

Pipeline:
    chat turn done  ->  asyncio.create_task(extract_and_persist(...))
        ->  LLM call (quarrel-cheap, JSON mode)
        ->  parse + validate against pydantic model
        ->  insert rows into user_facts (embedding column stays null;
            Phase C step 14 backfills + embeds new rows)

CLAUDE.md anchors:
    §7.2 — fact extraction runs on quarrel-cheap
    §6.2 — user_facts schema
    §9.4.1 — contradiction detection consumes these rows

Failures here are silent. Extraction is best-effort; an LLM hiccup must
NOT bubble to the user-facing chat turn.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

import structlog
from pydantic import BaseModel, Field, ValidationError
from supabase import AsyncClient

from app.prompts.fact_extraction import FACT_EXTRACTION_PROMPT
from app.services._db_typing import rows as _rows
from app.services.llm import (
    QUARREL_CHEAP,
    QUARREL_EMBED,
    LiteLLMClient,
    LiteLLMError,
    LiteLLMNetworkError,
    get_llm_client,
)
from app.services.supabase_client import get_supabase

log = structlog.get_logger(__name__)

# Mirrors packages/shared/src/schemas/enums.ts userFactCategorySchema.
FactCategory = Literal[
    "belief",
    "goal",
    "preference",
    "identity",
    "history",
    "commitment",
    "rationalization",
]


class ExtractedFact(BaseModel):
    fact: str = Field(min_length=1, max_length=500)
    category: FactCategory
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    supersedes_fact_id: int | None = None


class FactExtractionResult(BaseModel):
    facts: list[ExtractedFact] = Field(default_factory=list)


async def extract_facts(
    user_message: str,
    *,
    user_id: str | None = None,
    conversation_id: str | None = None,
    client: LiteLLMClient | None = None,
) -> FactExtractionResult:
    """Call the LLM and parse its JSON. Returns an empty result on any failure."""

    if not user_message.strip():
        return FactExtractionResult(facts=[])

    llm = client or get_llm_client()

    messages = [
        {"role": "system", "content": FACT_EXTRACTION_PROMPT},
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
                "generation_name": "fact_extraction",
                "trace_user_id": user_id,
                "session_id": conversation_id,
                "tags": ["fact_extraction"],
            },
        )
    except (LiteLLMError, LiteLLMNetworkError) as err:
        log.warning("facts.extract.llm_error", user_id=user_id, error=str(err))
        return FactExtractionResult(facts=[])

    try:
        raw_content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as err:
        log.warning("facts.extract.malformed_response", error=str(err))
        return FactExtractionResult(facts=[])

    if isinstance(raw_content, list):
        raw_content = "".join(
            block.get("text", "")
            for block in raw_content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    if not isinstance(raw_content, str):
        return FactExtractionResult(facts=[])

    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError:
        log.warning("facts.extract.json_decode_failed", raw=raw_content[:200])
        return FactExtractionResult(facts=[])

    try:
        return FactExtractionResult.model_validate(parsed)
    except ValidationError as err:
        log.warning("facts.extract.schema_invalid", error=str(err))
        return FactExtractionResult(facts=[])


async def persist_facts(
    supabase: AsyncClient,
    *,
    user_id: str,
    source_message_id: int | None,
    facts: list[ExtractedFact],
) -> list[tuple[int, str]]:
    """Insert extracted facts. Returns (id, fact_text) tuples in order.

    Empty list on insert failure — fact insertion is best-effort and
    embedding is owner of the follow-up backfill.
    """

    if not facts:
        return []

    payload = [
        {
            "user_id": user_id,
            "fact": f.fact,
            "category": f.category,
            "confidence": f.confidence,
            "source_message_id": source_message_id,
            "superseded_by": None,
            "is_active": True,
            # embedding stays null here — embed_facts() backfills below.
        }
        for f in facts
    ]

    try:
        res = await supabase.table("user_facts").insert(payload).execute()
    except Exception as err:  # noqa: BLE001 — best-effort path
        log.warning("facts.persist.failed", user_id=user_id, error=str(err))
        return []

    inserted = _rows(res.data)
    return [(int(row["id"]), str(row["fact"])) for row in inserted]


async def embed_facts(
    supabase: AsyncClient,
    *,
    facts: list[tuple[int, str]],
    client: LiteLLMClient | None = None,
) -> int:
    """Embed every fact in `facts` and write the vector to user_facts.embedding.

    Batches into a single /embeddings call. Failures are swallowed — the
    affected rows simply stay at embedding=null, which match_user_facts
    excludes from retrieval (the next chat turn with a similar query will
    not see them, but they're still on disk and a later backfill can fill).
    """

    if not facts:
        return 0

    llm = client or get_llm_client()
    inputs = [text for _, text in facts]

    try:
        vectors = await llm.embed(model=QUARREL_EMBED, input=inputs)
    except (LiteLLMError, LiteLLMNetworkError) as err:
        log.warning("facts.embed.llm_error", count=len(facts), error=str(err))
        return 0

    if len(vectors) != len(facts):
        log.warning(
            "facts.embed.length_mismatch",
            expected=len(facts),
            got=len(vectors),
        )
        return 0

    updated = 0
    for (fact_id, _), vector in zip(facts, vectors, strict=True):
        try:
            await (
                supabase.table("user_facts")
                .update({"embedding": vector})
                .eq("id", fact_id)
                .execute()
            )
            updated += 1
        except Exception as err:  # noqa: BLE001 — best-effort path
            log.warning("facts.embed.update_failed", fact_id=fact_id, error=str(err))
    return updated


async def extract_and_persist(
    *,
    user_id: str,
    conversation_id: str,
    user_message: str,
    source_message_id: int | None,
    client: LiteLLMClient | None = None,
    supabase: AsyncClient | None = None,
) -> int:
    """End-to-end: classify → persist → embed. Returns count of inserted facts.

    Module-level swap point used by `chat_stream` via `asyncio.create_task`.
    Tests monkeypatch this to run synchronously.
    """

    result = await extract_facts(
        user_message,
        user_id=user_id,
        conversation_id=conversation_id,
        client=client,
    )
    if not result.facts:
        return 0

    sb = supabase or await get_supabase()
    inserted = await persist_facts(
        sb,
        user_id=user_id,
        source_message_id=source_message_id,
        facts=result.facts,
    )
    if inserted:
        await embed_facts(sb, facts=inserted, client=client)
    return len(inserted)


__all__ = [
    "ExtractedFact",
    "FactCategory",
    "FactExtractionResult",
    "embed_facts",
    "extract_and_persist",
    "extract_facts",
    "persist_facts",
]
