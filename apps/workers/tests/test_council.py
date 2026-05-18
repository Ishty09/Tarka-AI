"""Council orchestration tests.

Stubs the LLM (with a stateful counter so successive calls return canned
content per slug) and Supabase (table-shaped fake). Covers parallel fan-
out, partial-failure tolerance, wipeout detection, judge defensive
fallback, and persistence shape.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.council import (
    COUNCIL_SLUGS,
    CouncilReply,
    CouncilWipeoutError,
    JudgeVerdict,
    persist_council_run,
    run_council,
    run_judge,
)
from app.services.llm import LiteLLMError, LiteLLMNetworkError


# ----- LLM stub --------------------------------------------------------------


class CouncilFakeLLM:
    """Returns different canned content based on a `tag` in metadata.

    Lookup priority for response selection:
      1. exact `metadata.generation_name` match
      2. failure injected via `failures` dict (raises)
    Default response is a generic "ok" string.
    """

    def __init__(
        self,
        *,
        responses: dict[str, str] | None = None,
        failures: dict[str, Exception] | None = None,
    ) -> None:
        self.responses = responses or {}
        self.failures = failures or {}
        self.calls: list[dict[str, Any]] = []

    async def chat(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        meta = kwargs.get("metadata") or {}
        name = str(meta.get("generation_name", ""))

        if name in self.failures:
            raise self.failures[name]

        content = self.responses.get(name) or "default reply"
        return {
            "choices": [{"message": {"role": "assistant", "content": content}}],
        }


# ----- Supabase fake --------------------------------------------------------


class _Res:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, table: "_Table", op: str, payload: Any = None) -> None:
        self._table = table
        self._op = op
        self._payload = payload
        self._filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None
        self._maybe_single = False

    def select(self, _cols: str = "*") -> "_Query":
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, "eq", val))
        return self

    def in_(self, col: str, vals: list[Any]) -> "_Query":
        self._filters.append((col, "in", vals))
        return self

    def limit(self, n: int) -> "_Query":
        self._limit = n
        return self

    def maybe_single(self) -> "_Query":
        self._maybe_single = True
        return self

    async def execute(self) -> _Res:
        if self._op == "select":
            rows = list(self._table.rows)
            for col, op, val in self._filters:
                if op == "eq":
                    rows = [r for r in rows if r.get(col) == val]
                elif op == "in":
                    rows = [r for r in rows if r.get(col) in val]
            if self._limit is not None:
                rows = rows[: self._limit]
            if self._maybe_single:
                return _Res(rows[0] if rows else None)
            return _Res(rows)

        if self._op == "insert":
            payload = self._payload if isinstance(self._payload, list) else [self._payload]
            inserted: list[dict[str, Any]] = []
            for row in payload:
                new_row = dict(row)
                if "id" not in new_row and self._table.name == "messages":
                    new_row["id"] = len(self._table.rows) + 1
                self._table.rows.append(new_row)
                inserted.append(new_row)
            return _Res(inserted)

        return _Res([])


class _Table:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, _cols: str = "*") -> _Query:
        return _Query(self, "select")

    def insert(self, payload: Any) -> _Query:
        return _Query(self, "insert", payload)


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, _Table] = {}

    def table(self, name: str) -> _Table:
        if name not in self.tables:
            self.tables[name] = _Table(name)
        return self.tables[name]

    def seed_personas(self) -> None:
        for slug in COUNCIL_SLUGS:
            self.table("personas").rows.append(
                {
                    "id": f"{slug}-id",
                    "slug": slug,
                    "system_prompt": f"You are {slug}.",
                }
            )


GOOD_VERDICT = {
    "conditions_for": ["Specific ask"],
    "conditions_against": ["Sunk cost talk"],
    "missing_information": ["Timeline"],
    "confidence": 7,
    "verdict": "You're going to do this anyway. Set the conditions first.",
}


def _all_council_responses() -> dict[str, str]:
    return {f"council.{slug}": f"{slug.replace('_', ' ')} says X." for slug in COUNCIL_SLUGS}


# ----- run_judge ------------------------------------------------------------


async def test_judge_parses_well_formed_output() -> None:
    llm = CouncilFakeLLM(responses={"council.judge": json.dumps(GOOD_VERDICT)})
    replies = [CouncilReply(slug=s, text=f"{s} reply") for s in COUNCIL_SLUGS]
    verdict = await run_judge(
        dilemma="x",
        replies=replies,
        client=llm,  # type: ignore[arg-type]
    )
    assert verdict is not None
    assert verdict.confidence == 7
    assert verdict.verdict.startswith("You're going to")


async def test_judge_llm_error_returns_none() -> None:
    llm = CouncilFakeLLM(failures={"council.judge": LiteLLMNetworkError("down")})
    verdict = await run_judge(dilemma="x", replies=[], client=llm)  # type: ignore[arg-type]
    assert verdict is None


async def test_judge_malformed_json_returns_none() -> None:
    llm = CouncilFakeLLM(responses={"council.judge": "not json"})
    verdict = await run_judge(dilemma="x", replies=[], client=llm)  # type: ignore[arg-type]
    assert verdict is None


# ----- run_council ----------------------------------------------------------


async def test_run_council_happy_path() -> None:
    sb = FakeSupabase()
    sb.seed_personas()

    responses = _all_council_responses()
    responses["council.judge"] = json.dumps(GOOD_VERDICT)
    llm = CouncilFakeLLM(responses=responses)

    run = await run_council(
        sb,  # type: ignore[arg-type]
        user_id="u",
        dilemma="Should I quit my job?",
        client=llm,  # type: ignore[arg-type]
    )

    # Five member calls + one judge = six LLM calls.
    assert len(llm.calls) == 6
    assert run.conversation_id is not None
    assert run.assistant_message_id is not None
    assert run.verdict.confidence == 7
    # All council replies came back.
    assert all(r.text for r in run.replies)
    # Conversation + 2 messages (user + assistant) persisted.
    assert len(sb.table("conversations").rows) == 1
    assert len(sb.table("messages").rows) == 2
    assistant_msg = sb.table("messages").rows[1]
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["metadata"]["kind"] == "council_verdict"
    assert len(assistant_msg["metadata"]["council"]) == 5


async def test_run_council_partial_failure_continues() -> None:
    sb = FakeSupabase()
    sb.seed_personas()

    responses = _all_council_responses()
    responses["council.judge"] = json.dumps(GOOD_VERDICT)
    # Two councilors fail; three return text.
    failures = {
        "council.the_stoic": LiteLLMNetworkError("down"),
        "council.the_economist": LiteLLMError("500", 500, "x"),
    }
    llm = CouncilFakeLLM(responses=responses, failures=failures)

    run = await run_council(
        sb,  # type: ignore[arg-type]
        user_id="u",
        dilemma="x" * 50,
        client=llm,  # type: ignore[arg-type]
    )

    text_replies = [r for r in run.replies if r.text]
    error_replies = [r for r in run.replies if r.error]
    assert len(text_replies) == 3
    assert len(error_replies) == 2
    # Run still persisted.
    assert run.conversation_id is not None


async def test_run_council_wipeout_raises() -> None:
    sb = FakeSupabase()
    sb.seed_personas()

    failures = {f"council.{slug}": LiteLLMNetworkError("down") for slug in COUNCIL_SLUGS}
    llm = CouncilFakeLLM(failures=failures)

    with pytest.raises(CouncilWipeoutError):
        await run_council(
            sb,  # type: ignore[arg-type]
            user_id="u",
            dilemma="x" * 50,
            client=llm,  # type: ignore[arg-type]
        )
    # No conversation persisted.
    assert sb.table("conversations").rows == []


async def test_run_council_judge_failure_yields_defensive_verdict() -> None:
    sb = FakeSupabase()
    sb.seed_personas()

    responses = _all_council_responses()
    llm = CouncilFakeLLM(
        responses=responses,
        failures={"council.judge": LiteLLMNetworkError("down")},
    )

    run = await run_council(
        sb,  # type: ignore[arg-type]
        user_id="u",
        dilemma="x" * 50,
        client=llm,  # type: ignore[arg-type]
    )

    assert run.verdict.confidence == 0
    assert "synthesis call failed" in run.verdict.verdict
    # Council replies still persisted.
    assistant_msg = sb.table("messages").rows[1]
    assert len(assistant_msg["metadata"]["council"]) == 5


async def test_persist_uses_skeptic_as_conversation_host() -> None:
    sb = FakeSupabase()
    sb.seed_personas()
    from app.services.council import CouncilRun

    run = CouncilRun(
        dilemma="x",
        replies=[CouncilReply(slug=s, text="ok") for s in COUNCIL_SLUGS],
        verdict=JudgeVerdict(**GOOD_VERDICT),
    )
    persisted = await persist_council_run(sb, user_id="u", run=run)  # type: ignore[arg-type]
    assert persisted.conversation_id is not None
    convo = sb.table("conversations").rows[0]
    assert convo["mode"] == "council"
    assert convo["persona_id"] == "the_skeptic-id"
    assert convo["metadata"]["roster"] == list(COUNCIL_SLUGS)
