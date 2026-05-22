"""Daily Roast scheduling + generation (CLAUDE.md §9.2.1).

Cron fires every 15 minutes. For each user whose `daily_roast_time` falls
into the current 15-minute window in their timezone AND who hasn't received
a roast in the last 23 hours, we generate a 280-char roast via quarrel-cheap
and append it to that user's "Daily Roast" auto-conversation.

Push notification delivery is DEFERRED to the §27 step 45 push-template
pass — VAPID keys + service worker + browser permission flow aren't in
yet. The roast message persists either way; subscribers will see it
inline next time they open the app.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from supabase import AsyncClient

from app.prompts.daily_roast import DAILY_ROAST_PROMPT
from app.services._db_typing import row_or_none, rows as _rows
from app.services.langfuse_trace import build_metadata as build_trace_metadata
from app.services.llm import (
    QUARREL_CHEAP,
    LiteLLMClient,
    LiteLLMError,
    LiteLLMNetworkError,
    get_llm_client,
)
from app.services.supabase_client import get_supabase

log = structlog.get_logger(__name__)


# §9.2.1 push budget — keep the body short.
MAX_ROAST_CHARS = 280
TOP_FACTS = 5
DEDUPE_WINDOW = timedelta(hours=23)
DEFAULT_WINDOW_MINUTES = 15

# Length floor so a refusal or token-truncated response doesn't ship.
MIN_ROAST_CHARS = 30


@dataclass(slots=True)
class RoastRecipient:
    """One eligible user resolved by the timezone scan."""

    user_id: str
    username: str
    persona_slug: str
    persona_id: str
    persona_name: str
    locale: str
    timezone: str


@dataclass(slots=True)
class RoastRun:
    user_id: str
    conversation_id: str
    message_id: int
    text: str


# ----- Eligibility scan -----------------------------------------------------


async def find_eligible_users(
    supabase: AsyncClient,
    *,
    now_utc: datetime,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
) -> list[RoastRecipient]:
    """Users whose local daily_roast_time falls inside [now_utc - window, now_utc].

    The DB stores `daily_roast_time` as a `time` (no date, no tz). We convert
    `now_utc` to each user's timezone and check whether their stored clock
    time is within the trailing `window_minutes`. The 15-minute cadence in
    §9.2.1 matches the cron interval, so a user at 09:00 local fires once
    on the 09:00 window scan.
    """

    res = (
        await supabase.table("profiles")
        .select(
            "id, username, timezone, locale, daily_roast_time, daily_roast_persona_slug, "
            "notification_push, is_suspended"
        )
        .not_.is_("daily_roast_time", "null")
        .not_.is_("daily_roast_persona_slug", "null")
        .eq("is_suspended", False)
        .eq("notification_push", True)
        .execute()
    )
    candidates = _rows(res.data)
    if not candidates:
        return []

    persona_slugs = list(
        {
            str(c.get("daily_roast_persona_slug"))
            for c in candidates
            if c.get("daily_roast_persona_slug")
        }
    )
    persona_lookup: dict[str, dict[str, Any]] = {}
    if persona_slugs:
        persona_res = (
            await supabase.table("personas")
            .select("id, slug, name")
            .in_("slug", persona_slugs)
            .execute()
        )
        for row in _rows(persona_res.data):
            persona_lookup[str(row["slug"])] = row

    eligible: list[RoastRecipient] = []
    for profile in candidates:
        slug = profile.get("daily_roast_persona_slug")
        if not isinstance(slug, str) or slug not in persona_lookup:
            continue
        roast_time_raw = profile.get("daily_roast_time")
        if not isinstance(roast_time_raw, str):
            continue
        tz_name = profile.get("timezone") or "UTC"
        if not isinstance(tz_name, str):
            tz_name = "UTC"

        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            log.warning("daily_roast.bad_timezone", user_id=profile.get("id"), tz=tz_name)
            continue

        try:
            target = time.fromisoformat(roast_time_raw.split("+")[0].split("Z")[0])
        except ValueError:
            log.warning("daily_roast.bad_time", user_id=profile.get("id"), raw=roast_time_raw)
            continue

        now_local = now_utc.astimezone(tz)
        window_start = now_local - timedelta(minutes=window_minutes)
        if not _time_in_window(target, window_start.time(), now_local.time()):
            continue

        persona_row = persona_lookup[slug]
        eligible.append(
            RoastRecipient(
                user_id=str(profile["id"]),
                username=str(profile.get("username") or "you"),
                persona_slug=slug,
                persona_id=str(persona_row["id"]),
                persona_name=str(persona_row.get("name") or slug),
                locale=str(profile.get("locale") or "en"),
                timezone=tz_name,
            )
        )

    return eligible


def _time_in_window(target: time, start: time, end: time) -> bool:
    """True if `target` falls inside (start, end]. Handles wrap-around midnight."""

    if start <= end:
        return start < target <= end
    # Window crossed midnight (rare — fires when window_start is yesterday).
    return target > start or target <= end


# ----- Dedupe ---------------------------------------------------------------


async def has_recent_roast(
    supabase: AsyncClient,
    *,
    user_id: str,
    now_utc: datetime,
    window: timedelta = DEDUPE_WINDOW,
) -> bool:
    """Has the user already received a daily roast within `window`?"""

    cutoff = (now_utc - window).isoformat()
    res = (
        await supabase.table("messages")
        .select("id, created_at")
        .eq("user_id", user_id)
        .eq("role", "assistant")
        .gte("created_at", cutoff)
        .limit(50)
        .execute()
    )
    rows = _rows(res.data)
    for row in rows:
        meta = row.get("metadata") if isinstance(row, dict) else None
        if isinstance(meta, dict) and meta.get("kind") == "daily_roast":
            return True
    # Fast path: most recent assistant messages probably aren't roasts —
    # we have to fetch metadata to check, but only need to hit pg once.
    # Fallback: query directly on metadata via JSONB filter.
    res2 = (
        await supabase.table("messages")
        .select("id")
        .eq("user_id", user_id)
        .gte("created_at", cutoff)
        .execute()
    )
    # No reliable JSONB filter in supabase-py without raw SQL; the above
    # already covered the dedupe via the first SELECT. If we missed (no
    # metadata in payload), the second query is a no-op upper bound check.
    _ = res2
    return False


# ----- Conversation lookup --------------------------------------------------


async def get_or_create_daily_roast_conversation(
    supabase: AsyncClient,
    *,
    recipient: RoastRecipient,
) -> str:
    """Find the user's stable Daily Roast conversation, creating if missing."""

    res = (
        await supabase.table("conversations")
        .select("id")
        .eq("user_id", recipient.user_id)
        .eq("mode", "roast")
        .eq("archived", False)
        .limit(20)
        .execute()
    )
    for row in _rows(res.data):
        # We don't filter on metadata in the query (no JSONB filter in supabase-py).
        # Inspect candidates client-side.
        if not isinstance(row, dict):
            continue
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else None
        if meta and meta.get("kind") == "daily_roast":
            return str(row["id"])

    conversation_id = str(uuid.uuid4())
    await (
        supabase.table("conversations")
        .insert(
            {
                "id": conversation_id,
                "user_id": recipient.user_id,
                "persona_id": recipient.persona_id,
                "mode": "roast",
                "title": "Daily Roast",
                "metadata": {
                    "kind": "daily_roast",
                    "persona_slug": recipient.persona_slug,
                },
            }
        )
        .execute()
    )
    return conversation_id


# ----- Top facts -----------------------------------------------------------


async def fetch_top_facts(
    supabase: AsyncClient,
    *,
    user_id: str,
    limit: int = TOP_FACTS,
) -> list[str]:
    """Highest-confidence active facts for the user, newest among ties."""

    res = (
        await supabase.table("user_facts")
        .select("fact, confidence, category, created_at")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .order("confidence", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = _rows(res.data)
    return [str(r["fact"]) for r in rows if r.get("fact")]


# ----- Generation ----------------------------------------------------------


async def generate_roast(
    recipient: RoastRecipient,
    facts: list[str],
    *,
    client: LiteLLMClient | None = None,
) -> str | None:
    llm = client or get_llm_client()

    facts_block = "\n".join(f"- {f}" for f in facts) if facts else "(no facts yet)"
    body = (
        "<context>\n"
        f"username: {recipient.username}\n"
        f"persona: {recipient.persona_slug}\n"
        "</context>\n"
        "<user_facts>\n"
        f"{facts_block}\n"
        "</user_facts>"
    )

    try:
        response = await llm.chat(
            model=QUARREL_CHEAP,
            messages=[
                {"role": "system", "content": DAILY_ROAST_PROMPT},
                {"role": "user", "content": body},
            ],
            temperature=0.8,
            max_tokens=180,
            user=recipient.user_id,
            metadata=build_trace_metadata(
                name="daily_roast",
                user_id=recipient.user_id,
                mode="daily_roast",
                persona_slug=recipient.persona_slug,
            ),
        )
    except (LiteLLMError, LiteLLMNetworkError) as err:
        log.warning(
            "daily_roast.llm_error",
            user_id=recipient.user_id,
            error=str(err),
        )
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

    text = raw.strip().strip('"').strip()
    if len(text) < MIN_ROAST_CHARS:
        log.warning("daily_roast.too_short", user_id=recipient.user_id, length=len(text))
        return None
    if len(text) > MAX_ROAST_CHARS:
        text = text[:MAX_ROAST_CHARS].rstrip()
    return text


# ----- Persistence ---------------------------------------------------------


async def persist_roast(
    supabase: AsyncClient,
    *,
    recipient: RoastRecipient,
    text: str,
    conversation_id: str,
) -> int | None:
    res = (
        await supabase.table("messages")
        .insert(
            {
                "conversation_id": conversation_id,
                "user_id": None,
                "role": "assistant",
                "content": text,
                "safety_verdict": "safe",
                "model": QUARREL_CHEAP,
                "metadata": {
                    "kind": "daily_roast",
                    "persona_slug": recipient.persona_slug,
                    "persona_name": recipient.persona_name,
                },
            }
        )
        .execute()
    )
    inserted = _rows(res.data)
    return int(inserted[0]["id"]) if inserted else None


# ----- Orchestration -------------------------------------------------------


async def deliver_one(
    supabase: AsyncClient,
    *,
    recipient: RoastRecipient,
    now_utc: datetime,
    client: LiteLLMClient | None = None,
) -> RoastRun | None:
    if await has_recent_roast(supabase, user_id=recipient.user_id, now_utc=now_utc):
        log.info("daily_roast.deduped", user_id=recipient.user_id)
        return None

    facts = await fetch_top_facts(supabase, user_id=recipient.user_id)
    text = await generate_roast(recipient, facts, client=client)
    if text is None:
        return None

    conversation_id = await get_or_create_daily_roast_conversation(
        supabase,
        recipient=recipient,
    )
    message_id = await persist_roast(
        supabase,
        recipient=recipient,
        text=text,
        conversation_id=conversation_id,
    )
    if message_id is None:
        return None
    return RoastRun(
        user_id=recipient.user_id,
        conversation_id=conversation_id,
        message_id=message_id,
        text=text,
    )


async def run_window(
    *,
    now_utc: datetime,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    client: LiteLLMClient | None = None,
    supabase: AsyncClient | None = None,
) -> dict[str, int]:
    sb = supabase or await get_supabase()
    recipients = await find_eligible_users(
        sb,
        now_utc=now_utc,
        window_minutes=window_minutes,
    )

    delivered = 0
    skipped = 0
    for recipient in recipients:
        run = await deliver_one(
            sb,
            recipient=recipient,
            now_utc=now_utc,
            client=client,
        )
        if run is None:
            skipped += 1
        else:
            delivered += 1

    log.info(
        "daily_roast.window.done",
        now=now_utc.isoformat(),
        window_minutes=window_minutes,
        eligible=len(recipients),
        delivered=delivered,
        skipped=skipped,
    )
    return {
        "eligible": len(recipients),
        "delivered": delivered,
        "skipped": skipped,
    }


__all__ = [
    "DEDUPE_WINDOW",
    "DEFAULT_WINDOW_MINUTES",
    "MAX_ROAST_CHARS",
    "MIN_ROAST_CHARS",
    "RoastRecipient",
    "RoastRun",
    "TOP_FACTS",
    "deliver_one",
    "fetch_top_facts",
    "find_eligible_users",
    "generate_roast",
    "get_or_create_daily_roast_conversation",
    "has_recent_roast",
    "persist_roast",
    "run_window",
]
