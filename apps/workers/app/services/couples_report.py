"""Weekly couples report — synthesises the trailing 7 days of activity
on each active couple_link into a structured digest.

Inputs per couple:
  - Health logs (effort 1-5 + appreciation/frustration notes)
  - Arbitrated or resolved disputes
  - Aggregate stats: total messages in shared chat (optional)

Output (jsonb): {
  themes: [string, ...]   # top recurring topics
  wins: [string, ...]     # things that worked
  watch: [string, ...]    # patterns to watch
  experiment: string      # one concrete experiment for the week
  effort_summary_a: string
  effort_summary_b: string
}

Idempotent per (couple_link_id, period_start). Skips couples that
already have a report for the window.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog

from app.config import get_settings
from app.services._db_typing import rows as _rows
from app.services.email import send_email
from app.services.langfuse_trace import build_metadata as build_trace_metadata
from app.services.llm import LiteLLMError, LiteLLMNetworkError, QUARREL_ARGUE, get_llm_client
from app.services.push import deliver_to_user
from app.services.supabase_client import get_supabase

log = structlog.get_logger(__name__)


REPORT_SYSTEM_PROMPT = """You are a couples therapist with anti-sycophant rules. Given the last 7 days of activity for a couple (effort check-ins, recent disputes, notes they wrote about each other), produce a weekly report both partners will read.

Output ONLY valid JSON matching the schema. Match the language the notes were written in.

Schema:
{
  "themes": [string, string, string]      // top 3 recurring topics this week
  "wins": [string, string]                  // things that worked
  "watch": [string, string]                 // patterns to watch — be honest, name them
  "experiment": string                     // one concrete thing both should try this week
  "effort_summary_a": string               // 1 sentence about partner A's effort
  "effort_summary_b": string               // 1 sentence about partner B's effort
}

Rules:
1. Both will see this — honest, not flattering.
2. If data is sparse, say so in `watch`. Don't manufacture insight.
3. If one partner barely engaged, name it in their effort_summary.
4. Themes should be specific (e.g. 'recurring money tension after Wednesday'), not vague ('communication').
"""


@dataclass(slots=True)
class CoupleReportResult:
    period_start: date
    period_end: date
    eligible: int
    inserted: int
    skipped: int


async def run_weekly() -> CoupleReportResult:
    """Generate one report per active couple_link for the trailing 7 days."""

    now = datetime.now(UTC)
    period_end = now.date()
    period_start = period_end - timedelta(days=6)

    supabase = await get_supabase()

    # Active couple links.
    links_resp = await (
        supabase.table("couple_links")
        .select("id, user_a, user_b")
        .eq("status", "active")
        .execute()
    )
    links: list[dict[str, Any]] = list(_rows(links_resp))

    inserted = 0
    skipped = 0

    for link in links:
        link_id = link["id"]

        # Skip if a report already exists for this window.
        existing_resp = await (
            supabase.table("couple_reports")
            .select("id")
            .eq("couple_link_id", link_id)
            .eq("period_start", period_start.isoformat())
            .execute()
        )
        if list(_rows(existing_resp)):
            skipped += 1
            continue

        # Pull last-7-days inputs.
        logs_resp = await (
            supabase.table("couple_health_logs")
            .select("user_id, log_date, effort_rating, partner_appreciation, frustration")
            .eq("couple_link_id", link_id)
            .gte("log_date", period_start.isoformat())
            .lte("log_date", period_end.isoformat())
            .execute()
        )
        logs = list(_rows(logs_resp))

        disputes_resp = await (
            supabase.table("couple_disputes")
            .select("title, status, arbitration, resolved_at")
            .eq("couple_link_id", link_id)
            .gte("created_at", period_start.isoformat())
            .execute()
        )
        disputes = list(_rows(disputes_resp))

        # No activity at all → skip (don't manufacture a report for nothing).
        if not logs and not disputes:
            skipped += 1
            continue

        prompt_payload = _build_prompt(
            logs=logs,
            disputes=disputes,
            user_a=link["user_a"],
            user_b=link.get("user_b"),
        )

        try:
            client = get_llm_client()
            result = await client.chat(
                model=QUARREL_ARGUE,
                messages=[
                    {"role": "system", "content": REPORT_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt_payload},
                ],
                max_tokens=1500,
                response_format={"type": "json_object"},
                metadata=build_trace_metadata(
                    name="couples_report",
                    user_id=link["user_a"],
                    session_id=link_id,
                ),
            )
        except (LiteLLMError, LiteLLMNetworkError) as err:
            log.warning("couples_report.llm_error", link_id=link_id, error=str(err))
            skipped += 1
            continue

        try:
            content = json.loads(result["choices"][0]["message"]["content"])
        except (json.JSONDecodeError, KeyError, IndexError) as err:
            log.warning("couples_report.parse_failed", link_id=link_id, error=str(err))
            skipped += 1
            continue

        await (
            supabase.table("couple_reports")
            .insert(
                {
                    "couple_link_id": link_id,
                    "period_start": period_start.isoformat(),
                    "period_end": period_end.isoformat(),
                    "content": content,
                    "generation_model": result.get("model", QUARREL_ARGUE),
                }
            )
            .execute()
        )
        inserted += 1

        # Best-effort: notify both partners. Failures don't poison the
        # rest of the batch — keep iterating through other couples.
        try:
            await _notify_report_ready(
                supabase,
                link_id=link_id,
                user_a=link["user_a"],
                user_b=link.get("user_b"),
                period_start=period_start,
                period_end=period_end,
            )
        except Exception as err:  # pragma: no cover - non-fatal
            log.warning(
                "couples_report.notify_failed", link_id=link_id, error=str(err)
            )

    return CoupleReportResult(
        period_start=period_start,
        period_end=period_end,
        eligible=len(links),
        inserted=inserted,
        skipped=skipped,
    )


def _build_prompt(
    *,
    logs: list[dict[str, Any]],
    disputes: list[dict[str, Any]],
    user_a: str,
    user_b: str | None,
) -> str:
    lines: list[str] = []
    lines.append(f"Partner A id: {user_a}")
    if user_b:
        lines.append(f"Partner B id: {user_b}")

    lines.append("\n=== Daily check-ins (last 7 days) ===")
    for log_row in sorted(logs, key=lambda r: (r["log_date"], r["user_id"])):
        side = "A" if log_row["user_id"] == user_a else "B"
        line = f"[{log_row['log_date']}] Partner {side} — effort {log_row['effort_rating']}/5"
        if log_row.get("partner_appreciation"):
            line += f"  | appreciated: {log_row['partner_appreciation']}"
        if log_row.get("frustration"):
            line += f"  | frustrated: {log_row['frustration']}"
        lines.append(line)
    if not logs:
        lines.append("(no check-ins this week)")

    lines.append("\n=== Disputes ===")
    if not disputes:
        lines.append("(no disputes this week)")
    for d in disputes:
        lines.append(f"- '{d['title']}' status={d['status']}")
        arb = d.get("arbitration")
        if isinstance(arb, dict):
            if arb.get("summary"):
                lines.append(f"  summary: {arb['summary']}")
            if arb.get("patterns_detected"):
                lines.append(f"  patterns: {', '.join(arb['patterns_detected'])}")

    return "\n".join(lines)


async def _resolve_email(supabase: Any, user_id: str) -> str | None:
    try:
        res = await supabase.auth.admin.get_user_by_id(user_id)
    except Exception as err:  # pragma: no cover - non-fatal
        log.info("couples_report.email_lookup_failed", user_id=user_id, error=str(err))
        return None
    user_obj = getattr(res, "user", None) or getattr(res, "data", None)
    email_val = getattr(user_obj, "email", None) if user_obj else None
    return email_val if isinstance(email_val, str) and email_val else None


async def _notify_report_ready(
    supabase: Any,
    *,
    link_id: str,
    user_a: str,
    user_b: str | None,
    period_start: date,
    period_end: date,
) -> None:
    """Push + email both partners that the weekly report is ready.

    Idempotency keys include period_start so a re-run of the same week
    can't double-notify, but a fresh week is treated as a new event.
    """

    app_url = str(get_settings().app_url).rstrip("/")
    report_url = f"{app_url}/couples/{link_id}/reports"
    p_start = period_start.isoformat()
    p_end = period_end.isoformat()

    for user_id in (user_a, user_b):
        if not user_id:
            continue
        try:
            await deliver_to_user(
                user_id=user_id,
                template="couples_report_ready",
                variables={},
                deep_link=report_url,
                idempotency_key=f"push:couples_report_ready:{link_id}:{p_start}:{user_id}",
                supabase=supabase,
            )
        except Exception as err:  # pragma: no cover - non-fatal
            log.warning(
                "couples_report.push_failed", user_id=user_id, error=str(err)
            )

        email_addr = await _resolve_email(supabase, user_id)
        if not email_addr:
            continue
        try:
            await send_email(
                template="couples_report_ready",
                to_email=email_addr,
                variables={
                    "report_url": report_url,
                    "period_start": p_start,
                    "period_end": p_end,
                },
                user_id=user_id,
                idempotency_key=f"email:couples_report_ready:{link_id}:{p_start}:{user_id}",
                supabase=supabase,
            )
        except Exception as err:  # pragma: no cover - non-fatal
            log.warning(
                "couples_report.email_failed", user_id=user_id, error=str(err)
            )
