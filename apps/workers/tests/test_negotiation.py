"""Negotiation Sparring service tests.

Stubs LLM + Supabase. Covers scenario lookup, session start (with override
landing in metadata), and critique generation + persistence.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.llm import LiteLLMError, LiteLLMNetworkError
from app.services.negotiation import (
    CritiqueResult,
    NotANegotiationError,
    UnknownScenarioError,
    generate_critique,
    get_scenario,
    list_scenarios,
    run_critique,
    start_session,
)


HOST_SLUG = "devils_advocate"

GOOD_CRITIQUE = {
    "strengths": [
        "Anchored hard on $X early.",
        "Used silence after the counter.",
        "Named the BATNA without flinching.",
    ],
    "weaknesses": [
        "Justified the ask twice in one breath.",
        "Conceded on signing bonus first.",
        "Smoothed over the awkwardness instead of holding the line.",
    ],
    "alternative": (
        "Open with a single number and a one-sentence reason, then stop talking. Let "
        "them carry the next 15 seconds. If they pivot, anchor again — don't trade ranges."
    ),
}


# ----- Fakes ----------------------------------------------------------------


class FakeLLM:
    def __init__(self, content: str | None = None, exc: Exception | None = None) -> None:
        self._content = content
        self._exc = exc
        self.calls: list[dict[str, Any]] = []

    async def chat(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        return {"choices": [{"message": {"role": "assistant", "content": self._content}}]}


class _Res:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, table: "_Table", op: str, payload: Any = None) -> None:
        self._table = table
        self._op = op
        self._payload = payload
        self._filters: list[tuple[str, Any]] = []
        self._limit: int | None = None
        self._maybe_single = False
        self._order_desc = False

    def select(self, _cols: str = "*") -> "_Query":
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, val))
        return self

    def order(self, _col: str, desc: bool = False) -> "_Query":
        self._order_desc = desc
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
            for col, val in self._filters:
                rows = [r for r in rows if r.get(col) == val]
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

    def seed_host(self) -> None:
        self.table("personas").rows.append({"id": "host-id", "slug": HOST_SLUG})


# ----- Scenario lookup ------------------------------------------------------


def test_list_scenarios_returns_all_ten() -> None:
    scenarios = list_scenarios()
    assert len(scenarios) == 10
    slugs = {s.slug for s in scenarios}
    assert "salary" in slugs
    assert "quit_job" in slugs


def test_get_scenario_unknown_raises() -> None:
    with pytest.raises(UnknownScenarioError):
        get_scenario("definitely_not_a_scenario")


# ----- start_session --------------------------------------------------------


async def test_start_session_writes_override_into_metadata() -> None:
    sb = FakeSupabase()
    sb.seed_host()
    result = await start_session(
        sb,  # type: ignore[arg-type]
        user_id="u",
        scenario_slug="salary",
    )

    assert result.scenario.slug == "salary"
    convo = sb.table("conversations").rows[0]
    assert convo["mode"] == "negotiate"
    assert convo["title"] == "Salary negotiation"
    meta = convo["metadata"]
    assert meta["scenario_slug"] == "salary"
    assert meta["counterparty"] == "hiring manager"
    assert "hiring manager" in meta["system_prompt_override"].lower()

    # Opening line landed as the first assistant message.
    msgs = sb.table("messages").rows
    assert len(msgs) == 1
    assert msgs[0]["role"] == "assistant"
    assert msgs[0]["metadata"]["kind"] == "negotiation_opening"
    assert msgs[0]["content"].startswith("Thanks for circling back")


async def test_start_session_unknown_scenario_raises() -> None:
    sb = FakeSupabase()
    sb.seed_host()
    with pytest.raises(UnknownScenarioError):
        await start_session(
            sb,  # type: ignore[arg-type]
            user_id="u",
            scenario_slug="nope",
        )


# ----- generate_critique ----------------------------------------------------


async def test_generate_critique_parses_well_formed() -> None:
    scenario = get_scenario("salary")
    llm = FakeLLM(content=json.dumps(GOOD_CRITIQUE))
    crit = await generate_critique(
        scenario=scenario,
        user_turns=["My target is X.", "I'll need to think about that."],
        client=llm,  # type: ignore[arg-type]
    )
    assert crit is not None
    assert len(crit.strengths) == 3
    assert len(crit.weaknesses) == 3
    assert "anchor" in crit.alternative.lower()


async def test_generate_critique_no_turns_returns_none() -> None:
    scenario = get_scenario("salary")
    llm = FakeLLM(content=json.dumps(GOOD_CRITIQUE))
    crit = await generate_critique(
        scenario=scenario,
        user_turns=[],
        client=llm,  # type: ignore[arg-type]
    )
    assert crit is None
    assert llm.calls == []


async def test_generate_critique_llm_error_returns_none() -> None:
    scenario = get_scenario("salary")
    llm = FakeLLM(exc=LiteLLMNetworkError("down"))
    assert (
        await generate_critique(
            scenario=scenario,
            user_turns=["x"],
            client=llm,  # type: ignore[arg-type]
        )
    ) is None


async def test_generate_critique_http_error_returns_none() -> None:
    scenario = get_scenario("salary")
    llm = FakeLLM(exc=LiteLLMError("500", 500, "x"))
    assert (
        await generate_critique(
            scenario=scenario,
            user_turns=["x"],
            client=llm,  # type: ignore[arg-type]
        )
    ) is None


async def test_generate_critique_two_strengths_rejected() -> None:
    bad = dict(GOOD_CRITIQUE)
    bad["strengths"] = GOOD_CRITIQUE["strengths"][:2]
    llm = FakeLLM(content=json.dumps(bad))
    assert (
        await generate_critique(
            scenario=get_scenario("salary"),
            user_turns=["x"],
            client=llm,  # type: ignore[arg-type]
        )
    ) is None


# ----- run_critique end-to-end ----------------------------------------------


async def _seed_session(sb: FakeSupabase, *, user_id: str = "u") -> str:
    sb.seed_host()
    result = await start_session(
        sb,  # type: ignore[arg-type]
        user_id=user_id,
        scenario_slug="salary",
    )
    return result.conversation_id


async def test_run_critique_happy_path_persists_message() -> None:
    sb = FakeSupabase()
    convo_id = await _seed_session(sb)
    # Add some user turns.
    sb.table("messages").rows.append(
        {
            "id": 99,
            "conversation_id": convo_id,
            "role": "user",
            "content": "My target is $200k.",
            "created_at": "2026-05-18T00:00:00Z",
        }
    )
    sb.table("messages").rows.append(
        {
            "id": 100,
            "conversation_id": convo_id,
            "role": "user",
            "content": "I've got a competing offer at $210k.",
            "created_at": "2026-05-18T00:01:00Z",
        }
    )

    llm = FakeLLM(content=json.dumps(GOOD_CRITIQUE))
    run = await run_critique(
        sb,  # type: ignore[arg-type]
        user_id="u",
        conversation_id=convo_id,
        client=llm,  # type: ignore[arg-type]
    )
    assert run is not None
    assert run.scenario.slug == "salary"
    assert run.assistant_message_id is not None

    # Critique message persisted with the right kind marker.
    critique_msgs = [
        m for m in sb.table("messages").rows
        if isinstance(m.get("metadata"), dict)
        and m["metadata"].get("kind") == "negotiation_critique"
    ]
    assert len(critique_msgs) == 1
    body = critique_msgs[0]["content"]
    assert "## Strengths" in body
    assert "## Weaknesses" in body
    assert "## What to try next time" in body


async def test_run_critique_other_user_raises() -> None:
    sb = FakeSupabase()
    convo_id = await _seed_session(sb, user_id="owner")
    llm = FakeLLM(content=json.dumps(GOOD_CRITIQUE))
    with pytest.raises(NotANegotiationError):
        await run_critique(
            sb,  # type: ignore[arg-type]
            user_id="someone-else",
            conversation_id=convo_id,
            client=llm,  # type: ignore[arg-type]
        )


async def test_run_critique_wrong_mode_raises() -> None:
    sb = FakeSupabase()
    sb.seed_host()
    sb.table("conversations").rows.append(
        {
            "id": "abc",
            "user_id": "u",
            "mode": "argue",
            "metadata": {"scenario_slug": "salary"},
        }
    )
    with pytest.raises(NotANegotiationError):
        await run_critique(
            sb,  # type: ignore[arg-type]
            user_id="u",
            conversation_id="abc",
            client=FakeLLM(),  # type: ignore[arg-type]
        )


async def test_run_critique_llm_failure_returns_none() -> None:
    sb = FakeSupabase()
    convo_id = await _seed_session(sb)
    sb.table("messages").rows.append(
        {
            "id": 99,
            "conversation_id": convo_id,
            "role": "user",
            "content": "Turn.",
            "created_at": "2026-05-18T00:00:00Z",
        }
    )
    llm = FakeLLM(exc=LiteLLMNetworkError("down"))
    run = await run_critique(
        sb,  # type: ignore[arg-type]
        user_id="u",
        conversation_id=convo_id,
        client=llm,  # type: ignore[arg-type]
    )
    assert run is None
    # No critique message persisted.
    assert all(
        not (
            isinstance(m.get("metadata"), dict)
            and m["metadata"].get("kind") == "negotiation_critique"
        )
        for m in sb.table("messages").rows
    )


# ----- CritiqueResult schema -----------------------------------------------


def test_critique_result_rejects_too_many_strengths() -> None:
    with pytest.raises(Exception):  # pydantic ValidationError
        CritiqueResult(
            strengths=["a", "b", "c", "d"],
            weaknesses=["x", "y", "z"],
            alternative="some alternative approach that is long enough to pass.",
        )
