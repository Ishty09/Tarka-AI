"""Couples cross-fact retrieval tests.

The actual triple-consent check lives in the SQL function
get_couple_facts() — we stub the RPC here and verify our wrapper:
  - empty bundle on RPC failure (consent gate raises in plpgsql)
  - empty bundle on zero rows
  - A/B labelling using the link's user_a/user_b
  - id list populated for downstream contradiction lookup
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.memory import UserFactsBundle, load_couple_facts


class _Res:
    def __init__(self, data: Any) -> None:
        self.data = data


class _LinkQuery:
    def __init__(self, table: "_Table") -> None:
        self._table = table
        self._filters: list[tuple[str, Any]] = []
        self._maybe_single = False

    def select(self, _cols: str = "*") -> "_LinkQuery":
        return self

    def eq(self, col: str, val: Any) -> "_LinkQuery":
        self._filters.append((col, val))
        return self

    def maybe_single(self) -> "_LinkQuery":
        self._maybe_single = True
        return self

    async def execute(self) -> _Res:
        rows = list(self._table.rows)
        for col, val in self._filters:
            rows = [r for r in rows if r.get(col) == val]
        if self._maybe_single:
            return _Res(rows[0] if rows else None)
        return _Res(rows)


class _Table:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def select(self, _cols: str = "*") -> _LinkQuery:
        return _LinkQuery(self)


class _RpcQuery:
    def __init__(self, fake: "FakeSupabase", name: str) -> None:
        self._fake = fake
        self._name = name

    async def execute(self) -> _Res:
        if self._name in self._fake.rpc_errors:
            raise self._fake.rpc_errors[self._name]
        return _Res(self._fake.rpc_results.get(self._name, []))


class FakeSupabase:
    def __init__(self) -> None:
        self._link_table = _Table()
        self.rpc_results: dict[str, list[dict[str, Any]]] = {}
        self.rpc_errors: dict[str, Exception] = {}

    def table(self, name: str) -> _Table:
        if name == "couple_links":
            return self._link_table
        return _Table()

    def rpc(self, name: str, _params: dict[str, Any] | None = None) -> _RpcQuery:
        return _RpcQuery(self, name)


# ----- tests ---------------------------------------------------------------


async def test_returns_empty_when_rpc_raises_consent_gate() -> None:
    """get_couple_facts raises in plpgsql when consent is missing —
    load_couple_facts swallows it and returns an empty bundle.
    """

    sb = FakeSupabase()
    sb.rpc_errors["get_couple_facts"] = RuntimeError("Cross-fact consent missing")
    bundle = await load_couple_facts(sb, link_id="link-1")  # type: ignore[arg-type]
    assert bundle == UserFactsBundle(text="", count=0, fact_ids=[])


async def test_returns_empty_when_rpc_returns_no_rows() -> None:
    sb = FakeSupabase()
    sb.rpc_results["get_couple_facts"] = []
    bundle = await load_couple_facts(sb, link_id="link-1")  # type: ignore[arg-type]
    assert bundle.count == 0


async def test_labels_facts_with_a_and_b() -> None:
    sb = FakeSupabase()
    sb._link_table.rows.append({
        "id": "link-1",
        "user_a": "user-a",
        "user_b": "user-b",
    })
    sb.rpc_results["get_couple_facts"] = [
        {
            "id": 10,
            "owner_id": "user-a",
            "fact": "User A said they hate Mondays.",
            "category": "belief",
            "confidence": 0.92,
            "created_at": "2026-04-01T00:00:00+00:00",
        },
        {
            "id": 11,
            "owner_id": "user-b",
            "fact": "User B committed to weekly date nights.",
            "category": "commitment",
            "confidence": 0.81,
            "created_at": "2026-04-15T00:00:00+00:00",
        },
    ]

    bundle = await load_couple_facts(sb, link_id="link-1")  # type: ignore[arg-type]
    assert bundle.count == 2
    assert "[partner=A, belief]" in bundle.text
    assert "[partner=B, commitment]" in bundle.text
    assert "User A said they hate Mondays." in bundle.text
    assert "User B committed to weekly date nights." in bundle.text
    assert "conf=0.92" in bundle.text
    assert "since 2026-04-01" in bundle.text
    assert bundle.fact_ids == [10, 11]


async def test_unknown_owner_labelled_with_question_mark() -> None:
    """Defensive: if get_couple_facts returns a row whose owner isn't
    user_a or user_b (shouldn't happen, but database state can drift),
    fall back to a '?' label rather than crashing or attributing wrong.
    """

    sb = FakeSupabase()
    sb._link_table.rows.append({
        "id": "link-1",
        "user_a": "user-a",
        "user_b": "user-b",
    })
    sb.rpc_results["get_couple_facts"] = [
        {
            "id": 99,
            "owner_id": "stray-user",
            "fact": "drift",
            "category": "belief",
            "confidence": 0.5,
            "created_at": "2026-04-01",
        }
    ]
    bundle = await load_couple_facts(sb, link_id="link-1")  # type: ignore[arg-type]
    assert "[partner=?, belief]" in bundle.text


async def test_caps_at_limit() -> None:
    sb = FakeSupabase()
    sb._link_table.rows.append({"id": "link-1", "user_a": "u-a", "user_b": "u-b"})
    sb.rpc_results["get_couple_facts"] = [
        {
            "id": i,
            "owner_id": "u-a",
            "fact": f"fact-{i}",
            "category": "belief",
            "confidence": 0.5,
            "created_at": "2026-01-01",
        }
        for i in range(40)
    ]
    bundle = await load_couple_facts(sb, link_id="link-1", limit=10)  # type: ignore[arg-type]
    # Count reflects raw RPC rows; lines and fact_ids reflect the cap.
    assert bundle.count == 40
    assert len(bundle.fact_ids) == 10
    assert bundle.text.count("\n") == 9  # 10 lines = 9 newlines
