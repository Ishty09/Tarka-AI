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

from app.services.memory import UserFactsBundle, load_user_facts


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
