"""Langfuse trace metadata builder (CLAUDE.md §21, §27 step 62).

Every LLM call goes through LiteLLM, which forwards the request's
`metadata` block to Langfuse via the success/failure callback wired in
infra/litellm-config.yaml. Langfuse interprets a known set of keys:

  - `generation_name` → trace.generation.name (we use it for the §21
    `name` field, e.g. ``argue.devils_advocate``, ``eulogy``)
  - `trace_user_id`   → trace.user_id
  - `session_id`      → trace.session_id (we use conversation_id)
  - `tags`            → trace.tags (a flat list of strings)
  - any other key     → trace.metadata.<key>

This helper centralises the shape so the 20+ call sites stay consistent
and so `cached_tokens` / `fallback_used` / `model_used` (per §21) land
in metadata wherever the upstream call has them.
"""

from __future__ import annotations

from typing import Any


def build_metadata(
    *,
    name: str,
    user_id: str | None = None,
    session_id: str | None = None,
    mode: str | None = None,
    persona_slug: str | None = None,
    tier: str | None = None,
    locale: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the metadata dict ready to pass to LiteLLMClient.chat(metadata=…).

    `tags` is constructed from whichever §21 fields are non-empty so a
    callsite that knows the persona but not the locale doesn't ship
    ``[None, "devils_advocate", None, None]``.
    """

    metadata: dict[str, Any] = {"generation_name": name}
    if user_id:
        metadata["trace_user_id"] = user_id
    if session_id:
        metadata["session_id"] = session_id

    tags: list[str] = []
    if mode:
        tags.append(mode)
    if persona_slug:
        tags.append(persona_slug)
    if tier:
        tags.append(tier)
    if locale:
        tags.append(locale)
    if tags:
        metadata["tags"] = tags

    if extra:
        # Extras are merged at the top level so Langfuse surfaces them as
        # trace.metadata.<key>. `cached_tokens`, `fallback_used`, and
        # `model_used` are the §21 reserved keys but the helper doesn't
        # restrict the set — call sites pass what they have.
        for key, value in extra.items():
            if value is None:
                continue
            metadata[key] = value

    return metadata
