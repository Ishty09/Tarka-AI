"""User-facts retrieval tests.

Stubs the LLM embed call and the Supabase RPC. load_user_facts must:
    - return empty bundle on empty input
    - call /embeddings once for the query, then RPC match_user_facts
    - format matches into the §7.3 user_facts block
    - swallow LLM / RPC errors and return empty
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.memory import (
    ContradictionCallout,
    UserFactsBundle,
    find_relevant_contradiction,
    load_user_facts,
    mark_contradiction_surfaced,
)


class _Res:
    def __init__(self, data: Any) -> None:
        self.data = data


class _RpcQuery:
    def __init__(self, fake: "FakeSupabase", name: str, params: dict[str, Any]) -> None:
        self._fake = fake
        self._name = name
        self._params = params

    async def execute(self) -> _Res:
        self._fake.rpc_calls.append({"name": self._name, "params": self._params})
        return _Res(self._fake.rpc_results.get(self._name, []))


class FakeSupabase:
    def __init__(self) -> None:
        self.rpc_results: dict[str, list[dict[str, Any]]] = {}
        self.rpc_calls: list[dict[str, Any]] = []

    def rpc(self, name: str, params: dict[str, Any] | None = None) -> _RpcQuery:
        return _RpcQuery(self, name, params or {})


class StubLLM:
    def __init__(self, *, vector: list[float] | None = None, exc: Exception | None = None) -> None:
        self._vector = vector
        self._exc = exc
        self.calls: list[dict[str, Any]] = []

    async def embed(self, **kwargs: Any) -> list[list[float]]:
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        return [self._vector or [0.0] * 1536]


# ----- tests -----------------------------------------------------------------


async def test_empty_query_returns_empty_bundle() -> None:
    sb = FakeSupabase()
    llm = StubLLM()
    bundle = await load_user_facts(
        sb,  # type: ignore[arg-type]
        "user-1",
        query_message="",
        client=llm,  # type: ignore[arg-type]
    )
    assert bundle == UserFactsBundle(text="", count=0)
    assert llm.calls == []
    assert sb.rpc_calls == []


async def test_formats_matched_facts() -> None:
    sb = FakeSupabase()
    sb.rpc_results["match_user_facts"] = [
        {
            "id": 1,
            "fact": "User hates Mondays.",
            "category": "belief",
            "confidence": 0.9,
            "similarity": 0.88,
            "created_at": "2026-05-01T00:00:00+00:00",
        },
        {
            "id": 2,
            "fact": "User committed to gym 3x/week.",
            "category": "commitment",
            "confidence": 0.75,
            "similarity": 0.61,
            "created_at": "2026-04-15T00:00:00+00:00",
        },
    ]
    bundle = await load_user_facts(
        sb,  # type: ignore[arg-type]
        "user-1",
        query_message="how was your monday",
        client=StubLLM(),  # type: ignore[arg-type]
    )
    assert bundle.count == 2
    assert "[belief] User hates Mondays." in bundle.text
    assert "[commitment] User committed to gym 3x/week." in bundle.text
    assert "since 2026-05-01" in bundle.text
    assert "conf=0.90" in bundle.text
    assert bundle.fact_ids == [1, 2]


async def test_zero_matches_returns_empty() -> None:
    sb = FakeSupabase()
    sb.rpc_results["match_user_facts"] = []
    bundle = await load_user_facts(
        sb,  # type: ignore[arg-type]
        "user-1",
        query_message="hello",
        client=StubLLM(),  # type: ignore[arg-type]
    )
    assert bundle == UserFactsBundle(text="", count=0)


async def test_passes_correct_rpc_params() -> None:
    sb = FakeSupabase()
    vector = [0.5] * 1536
    await load_user_facts(
        sb,  # type: ignore[arg-type]
        "user-99",
        query_message="anything",
        limit=5,
        min_similarity=0.4,
        client=StubLLM(vector=vector),  # type: ignore[arg-type]
    )
    assert len(sb.rpc_calls) == 1
    params = sb.rpc_calls[0]["params"]
    assert params["p_user_id"] == "user-99"
    assert params["p_match_count"] == 5
    assert params["p_min_similarity"] == pytest.approx(0.4)
    assert params["p_query_embedding"] == vector


async def test_embed_error_returns_empty() -> None:
    from app.services.llm import LiteLLMNetworkError

    sb = FakeSupabase()
    llm = StubLLM(exc=LiteLLMNetworkError("down"))
    bundle = await load_user_facts(
        sb,  # type: ignore[arg-type]
        "user-1",
        query_message="anything",
        client=llm,  # type: ignore[arg-type]
    )
    assert bundle == UserFactsBundle(text="", count=0)
    assert sb.rpc_calls == []


async def test_rpc_error_returns_empty() -> None:
    class ExplodingSupabase:
        def rpc(self, *_args: Any, **_kwargs: Any) -> Any:
            class _Q:
                async def execute(self) -> Any:
                    raise RuntimeError("postgres exploded")

            return _Q()

    bundle = await load_user_facts(
        ExplodingSupabase(),  # type: ignore[arg-type]
        "user-1",
        query_message="anything",
        client=StubLLM(),  # type: ignore[arg-type]
    )
    assert bundle == UserFactsBundle(text="", count=0)


# ----- find_relevant_contradiction ------------------------------------------


class _CQuery:
    """Capability subset the find_relevant_contradiction call exercises."""

    def __init__(self, table: "_CTable") -> None:
        self._table = table
        self._filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None
        self._or_clause: str | None = None
        self._payload: Any = None
        self._op = "select"

    def select(self, _cols: str = "*") -> "_CQuery":
        return self

    def eq(self, col: str, val: Any) -> "_CQuery":
        self._filters.append((col, "eq", val))
        return self

    def gte(self, col: str, val: Any) -> "_CQuery":
        self._filters.append((col, "gte", val))
        return self

    def is_(self, col: str, val: Any) -> "_CQuery":
        # "null" string is how supabase-py spells IS NULL.
        if val == "null":
            self._filters.append((col, "is_null", None))
        else:
            self._filters.append((col, "is", val))
        return self

    def or_(self, clause: str) -> "_CQuery":
        self._or_clause = clause
        return self

    def order(self, _col: str, desc: bool = False) -> "_CQuery":
        self._desc = desc
        return self

    def limit(self, n: int) -> "_CQuery":
        self._limit = n
        return self

    def update(self, payload: Any) -> "_CQuery":
        self._op = "update"
        self._payload = payload
        return self

    async def execute(self) -> _Res:
        rows = list(self._table.rows)
        for col, op, val in self._filters:
            if op == "eq":
                rows = [r for r in rows if r.get(col) == val]
            elif op == "is_null":
                rows = [r for r in rows if r.get(col) is None]
            elif op == "gte":
                rows = [r for r in rows if (r.get(col) or 0) >= val]

        if self._or_clause:
            # Format: fact_a_id.in.(1,2),fact_b_id.in.(1,2)
            ors: list[tuple[str, list[int]]] = []
            for fragment in self._or_clause.split(","):
                # naive split by ").in.(" then by "(" — we know the exact format
                # the production code uses.
                if ".in.(" in fragment:
                    col, rhs = fragment.split(".in.(", 1)
                    ids = [int(x) for x in rhs.rstrip(")").split(",") if x]
                    ors.append((col, ids))
            if ors:
                def matches_or(row: dict[str, Any]) -> bool:
                    for col, ids in ors:
                        if row.get(col) in ids:
                            return True
                    return False
                rows = [r for r in rows if matches_or(r)]

        if self._op == "update":
            for row in rows:
                row.update(self._payload)
            return _Res(rows)

        if self._limit is not None:
            rows = rows[: self._limit]
        return _Res(rows)


class _CTable:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, _cols: str = "*") -> _CQuery:
        return _CQuery(self)

    def update(self, payload: Any) -> _CQuery:
        return _CQuery(self).update(payload)


class CFakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, _CTable] = {}

    def table(self, name: str) -> _CTable:
        if name not in self.tables:
            self.tables[name] = _CTable(name)
        return self.tables[name]


async def test_find_relevant_contradiction_returns_top_match() -> None:
    sb = CFakeSupabase()
    sb.table("contradictions").rows.extend([
        {
            "id": 11,
            "user_id": "u",
            "severity": 8,
            "summary": "You said X then Y.",
            "fact_a_id": 1,
            "fact_b_id": 2,
            "surfaced_at": None,
            "dismissed_at": None,
            "fact_a": {"id": 1, "fact": "Fact A text", "created_at": "2026-04-01"},
            "fact_b": {"id": 2, "fact": "Fact B text", "created_at": "2026-05-01"},
        },
        {
            "id": 12,
            "user_id": "u",
            "severity": 9,  # higher, but doesn't touch fact_ids
            "summary": "irrelevant",
            "fact_a_id": 100,
            "fact_b_id": 200,
            "surfaced_at": None,
            "dismissed_at": None,
            "fact_a": {"id": 100, "fact": "x", "created_at": "x"},
            "fact_b": {"id": 200, "fact": "y", "created_at": "y"},
        },
    ])

    callout = await find_relevant_contradiction(
        sb,  # type: ignore[arg-type]
        "u",
        fact_ids=[1, 2],
    )
    assert callout is not None
    assert callout.id == 11
    assert callout.severity == 8
    assert callout.summary == "You said X then Y."
    assert callout.fact_a_text == "Fact A text"


async def test_find_relevant_contradiction_skips_surfaced_and_dismissed() -> None:
    sb = CFakeSupabase()
    sb.table("contradictions").rows.append({
        "id": 11,
        "user_id": "u",
        "severity": 9,
        "summary": "already shown",
        "fact_a_id": 1,
        "fact_b_id": 2,
        "surfaced_at": "2026-05-01T00:00:00+00:00",
        "dismissed_at": None,
        "fact_a": {"id": 1, "fact": "a", "created_at": "x"},
        "fact_b": {"id": 2, "fact": "b", "created_at": "y"},
    })
    callout = await find_relevant_contradiction(
        sb,  # type: ignore[arg-type]
        "u",
        fact_ids=[1, 2],
    )
    assert callout is None


async def test_find_relevant_contradiction_skips_below_threshold() -> None:
    sb = CFakeSupabase()
    sb.table("contradictions").rows.append({
        "id": 11,
        "user_id": "u",
        "severity": 3,  # below default min_severity=5
        "summary": "minor",
        "fact_a_id": 1,
        "fact_b_id": 2,
        "surfaced_at": None,
        "dismissed_at": None,
        "fact_a": {"id": 1, "fact": "a", "created_at": "x"},
        "fact_b": {"id": 2, "fact": "b", "created_at": "y"},
    })
    callout = await find_relevant_contradiction(
        sb,  # type: ignore[arg-type]
        "u",
        fact_ids=[1, 2],
    )
    assert callout is None


async def test_find_relevant_contradiction_empty_fact_ids_returns_none() -> None:
    sb = CFakeSupabase()
    callout = await find_relevant_contradiction(sb, "u", fact_ids=[])  # type: ignore[arg-type]
    assert callout is None


async def test_mark_contradiction_surfaced_stamps_timestamp() -> None:
    sb = CFakeSupabase()
    sb.table("contradictions").rows.append({
        "id": 11,
        "surfaced_at": None,
    })
    await mark_contradiction_surfaced(sb, 11)  # type: ignore[arg-type]
    row = sb.table("contradictions").rows[0]
    assert row["surfaced_at"] is not None
    # ContradictionCallout is exported for typing — touch it so the import
    # isn't reported as unused once future tests grow.
    _ = ContradictionCallout
