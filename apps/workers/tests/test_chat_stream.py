"""Integration tests for POST /chat/stream.

We stub the LLM and the Supabase client. The chat route owns the orchestration
logic — these tests verify each branch: auth, idempotency replay, quota
exhaustion, safety refusal, successful streaming, and conversation ownership.

The Supabase stub is a hand-rolled fake that supports the subset of the
builder API the route uses (table, select, eq, maybe_single, insert, update,
upsert, order, limit, execute). Mirrors postgrest-py shape but in-memory.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import llm as llm_module
from app.services import safety as safety_module
from app.services import supabase_client as supabase_module
from app.services.llm import ChatStreamDelta


# ----- Supabase fake ---------------------------------------------------------


class _ExecuteResult:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, table: "_Table", op: str) -> None:
        self._table = table
        self._op = op
        self._filters: list[tuple[str, Any]] = []
        self._select_columns: str = "*"
        self._payload: Any = None
        self._single = False
        self._maybe_single = False
        self._limit: int | None = None
        self._order: tuple[str, bool] | None = None

    def select(self, columns: str = "*") -> "_Query":
        self._select_columns = columns
        return self

    def insert(self, payload: Any) -> "_Query":
        self._payload = payload
        return self

    def update(self, payload: Any) -> "_Query":
        self._payload = payload
        return self

    def upsert(self, payload: Any, on_conflict: str | None = None) -> "_Query":
        self._op = "upsert"
        self._payload = payload
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, val))
        return self

    def in_(self, col: str, vals: list[Any]) -> "_Query":
        self._filters.append((col, ("__in__", vals)))
        return self

    def order(self, col: str, desc: bool = False) -> "_Query":
        self._order = (col, desc)
        return self

    def limit(self, n: int) -> "_Query":
        self._limit = n
        return self

    def maybe_single(self) -> "_Query":
        self._maybe_single = True
        return self

    def single(self) -> "_Query":
        self._single = True
        return self

    async def execute(self) -> _ExecuteResult:
        if self._op == "select":
            rows = list(self._table.rows)
            for col, val in self._filters:
                rows = [r for r in rows if r.get(col) == val]
            if self._order is not None:
                col, desc = self._order
                rows.sort(key=lambda r: r.get(col, 0), reverse=desc)
            if self._limit is not None:
                rows = rows[: self._limit]
            if self._maybe_single:
                return _ExecuteResult(rows[0] if rows else None)
            if self._single:
                return _ExecuteResult(rows[0])
            return _ExecuteResult(rows)

        if self._op == "insert":
            payload = self._payload if isinstance(self._payload, list) else [self._payload]
            inserted: list[dict[str, Any]] = []
            for row in payload:
                new_row = dict(row)
                if "id" not in new_row and self._table.name == "messages":
                    new_row["id"] = len(self._table.rows) + 1
                self._table.rows.append(new_row)
                inserted.append(new_row)
            return _ExecuteResult(inserted)

        if self._op == "update":
            for row in self._table.rows:
                if all(row.get(c) == v for c, v in self._filters):
                    row.update(self._payload)
            return _ExecuteResult([])

        if self._op == "upsert":
            payload = self._payload if isinstance(self._payload, list) else [self._payload]
            for row in payload:
                key = row.get("key") or row.get("id")
                existing = None
                for r in self._table.rows:
                    if (
                        (key is not None and (r.get("key") == key or r.get("id") == key))
                    ):
                        existing = r
                        break
                if existing is not None:
                    existing.update(row)
                else:
                    self._table.rows.append(dict(row))
            return _ExecuteResult([])

        raise RuntimeError(f"unknown op {self._op}")


class _Table:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, columns: str = "*") -> _Query:
        return _Query(self, "select").select(columns)

    def insert(self, payload: Any) -> _Query:
        return _Query(self, "insert").insert(payload)

    def update(self, payload: Any) -> _Query:
        return _Query(self, "update").update(payload)

    def upsert(self, payload: Any, on_conflict: str | None = None) -> _Query:
        return _Query(self, "upsert").upsert(payload, on_conflict=on_conflict)


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, _Table] = {}

    def table(self, name: str) -> _Table:
        if name not in self.tables:
            self.tables[name] = _Table(name)
        return self.tables[name]

    def seed(self, table: str, rows: list[dict[str, Any]]) -> None:
        self.table(table).rows.extend(rows)


# ----- LLM fake --------------------------------------------------------------


class FakeLLM:
    def __init__(self, *, safety_payload: dict[str, Any], stream_deltas: list[str]) -> None:
        self._safety_payload = safety_payload
        self._stream_deltas = stream_deltas
        self.chat_calls: list[dict[str, Any]] = []
        self.stream_calls: list[dict[str, Any]] = []

    async def chat(self, **kwargs: Any) -> dict[str, Any]:
        self.chat_calls.append(kwargs)
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(self._safety_payload),
                    }
                }
            ],
        }

    async def chat_stream(self, **kwargs: Any) -> AsyncIterator[ChatStreamDelta]:
        self.stream_calls.append(kwargs)
        for piece in self._stream_deltas:
            yield ChatStreamDelta(delta=piece, finish_reason=None, cached_tokens=None, raw={})
        yield ChatStreamDelta(delta="", finish_reason="stop", cached_tokens=12, raw={})


# ----- Fixtures --------------------------------------------------------------


PERSONA_ID = "11111111-1111-1111-1111-111111111111"
USER_ID = "22222222-2222-2222-2222-222222222222"
INTERNAL_SECRET = "test-secret"


@pytest.fixture
def fake_supabase() -> FakeSupabase:
    sb = FakeSupabase()
    sb.seed("profiles", [{"id": USER_ID, "tier": "free"}])
    sb.seed(
        "personas",
        [{"id": PERSONA_ID, "slug": "devils_advocate", "system_prompt": "ARGUE PROMPT"}],
    )
    return sb


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM(
        safety_payload={
            "verdict": "safe",
            "confidence": 0.99,
            "reason": "ok",
            "redactions": [],
        },
        stream_deltas=["Your ", "argument ", "is weak."],
    )


@pytest.fixture(autouse=True)
def wire_stubs(
    monkeypatch: pytest.MonkeyPatch, fake_supabase: FakeSupabase, fake_llm: FakeLLM
) -> None:
    # Settings need WORKERS_INTERNAL_SECRET set; everything else can stay default.
    monkeypatch.setenv("WORKERS_INTERNAL_SECRET", INTERNAL_SECRET)
    monkeypatch.setenv("NEXT_PUBLIC_APP_URL", "http://localhost:3000")
    monkeypatch.setenv("LITELLM_PROXY_URL", "http://localhost:4000")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "test-master")
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service")
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "test-anon")

    from app.config import get_settings

    get_settings.cache_clear()  # pick up patched env

    async def _get_supabase() -> Any:
        return fake_supabase

    monkeypatch.setattr(supabase_module, "get_supabase", _get_supabase)
    # The chat route imports get_supabase directly into its module namespace.
    from app.routes import chat as chat_route

    monkeypatch.setattr(chat_route, "get_supabase", _get_supabase)

    llm_module.set_llm_client(fake_llm)  # type: ignore[arg-type]
    monkeypatch.setattr(chat_route, "get_llm_client", lambda: fake_llm)
    # The safety service grabs the client via get_llm_client unless passed.
    monkeypatch.setattr(safety_module, "get_llm_client", lambda: fake_llm)

    yield
    llm_module.set_llm_client(None)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _post(client: TestClient, body: dict[str, Any], *, auth: str = INTERNAL_SECRET) -> Any:
    return client.post(
        "/chat/stream",
        json=body,
        headers={
            "authorization": f"Bearer {auth}",
            "x-user-id": USER_ID,
            "content-type": "application/json",
        },
    )


def _base_body() -> dict[str, Any]:
    return {
        "conversation_id": None,
        "persona_slug": "devils_advocate",
        "mode": "argue",
        "message": "I'm right about everything.",
        "idempotency_key": "abcdef123456",
    }


def _parse_sse(content: bytes) -> list[tuple[str, dict[str, Any]]]:
    """Split a streaming response into (event_name, payload) tuples."""

    out: list[tuple[str, dict[str, Any]]] = []
    text = content.decode("utf-8")
    for block in text.strip().split("\n\n"):
        if not block:
            continue
        event = ""
        data = ""
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line.removeprefix("event: ").strip()
            elif line.startswith("data: "):
                data = line.removeprefix("data: ").strip()
        out.append((event, json.loads(data) if data else {}))
    return out


# ----- Tests -----------------------------------------------------------------


def test_missing_bearer_returns_401(client: TestClient) -> None:
    res = client.post(
        "/chat/stream",
        json=_base_body(),
        headers={"x-user-id": USER_ID},
    )
    assert res.status_code == 401


def test_wrong_secret_returns_401(client: TestClient) -> None:
    res = _post(client, _base_body(), auth="wrong")
    assert res.status_code == 401


def test_missing_user_id_returns_401(client: TestClient) -> None:
    res = client.post(
        "/chat/stream",
        json=_base_body(),
        headers={"authorization": f"Bearer {INTERNAL_SECRET}"},
    )
    assert res.status_code == 401


def test_successful_stream_persists_messages_and_increments_quota(
    client: TestClient, fake_supabase: FakeSupabase, fake_llm: FakeLLM
) -> None:
    res = _post(client, _base_body())
    assert res.status_code == 200

    events = _parse_sse(res.content)
    delta_events = [e for e in events if e[0] == "delta"]
    done_events = [e for e in events if e[0] == "done"]
    assert len(delta_events) == 3
    assert "".join(e[1]["text"] for e in delta_events) == "Your argument is weak."
    assert len(done_events) == 1
    assert done_events[0][1]["finish_reason"] == "stop"

    # User message + assistant message both persisted.
    messages = fake_supabase.table("messages").rows
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["safety_verdict"] == "safe"
    assert messages[1]["role"] == "assistant"

    # Quota incremented by 1.
    quotas = fake_supabase.table("usage_quotas").rows
    assert len(quotas) == 1
    assert quotas[0]["messages_used"] == 1

    # Idempotency row stored with payload (used by replay test).
    idem = fake_supabase.table("idempotency_keys").rows
    assert any(row.get("response_body") is not None for row in idem)


def test_safety_crisis_short_circuits(
    client: TestClient, fake_supabase: FakeSupabase
) -> None:
    crisis_llm = FakeLLM(
        safety_payload={
            "verdict": "crisis",
            "confidence": 0.97,
            "reason": "suicidal ideation",
            "redactions": [],
        },
        stream_deltas=["should never appear"],
    )
    llm_module.set_llm_client(crisis_llm)  # type: ignore[arg-type]
    with patch("app.routes.chat.get_llm_client", lambda: crisis_llm), patch(
        "app.services.safety.get_llm_client", lambda: crisis_llm
    ):
        res = _post(client, _base_body())
    assert res.status_code == 200

    events = _parse_sse(res.content)
    kinds = [e[0] for e in events]
    assert "safety" in kinds
    assert "delta" not in kinds  # never streamed

    # User message persisted with crisis verdict; no assistant message.
    messages = fake_supabase.table("messages").rows
    assert len(messages) == 1
    assert messages[0]["safety_verdict"] == "crisis"


def test_quota_exceeded_returns_429(
    client: TestClient, fake_supabase: FakeSupabase
) -> None:
    from datetime import date

    fake_supabase.seed(
        "usage_quotas",
        [
            {
                "user_id": USER_ID,
                "period_start": date.today().isoformat(),
                "messages_used": 15,  # free-tier daily cap
            }
        ],
    )
    res = _post(client, _base_body())
    assert res.status_code == 429
    events = _parse_sse(res.content)
    assert events[0][0] == "quota_exceeded"
    assert events[0][1]["tier"] == "free"
    assert events[0][1]["limit"] == 15


def test_idempotency_replay_returns_stored_text(
    client: TestClient, fake_supabase: FakeSupabase
) -> None:
    res1 = _post(client, _base_body())
    assert res1.status_code == 200

    res2 = _post(client, _base_body())
    assert res2.status_code == 200
    events = _parse_sse(res2.content)
    # Replay path emits one delta with the full stored text, then done.
    delta_events = [e for e in events if e[0] == "delta"]
    assert delta_events
    assert delta_events[0][1]["text"] == "Your argument is weak."
    done = [e for e in events if e[0] == "done"]
    assert done and done[0][1]["finish_reason"] == "replay"

    # Quota wasn't double-incremented.
    quotas = fake_supabase.table("usage_quotas").rows
    assert quotas[0]["messages_used"] == 1


def test_unknown_persona_slug_returns_404(client: TestClient) -> None:
    body = _base_body()
    body["persona_slug"] = "does_not_exist"
    res = _post(client, body)
    assert res.status_code == 404


def test_existing_conversation_belongs_to_other_user_returns_403(
    client: TestClient, fake_supabase: FakeSupabase
) -> None:
    convo_id = "33333333-3333-3333-3333-333333333333"
    fake_supabase.seed(
        "conversations",
        [
            {
                "id": convo_id,
                "user_id": "someone-else",
                "persona_id": PERSONA_ID,
                "mode": "argue",
            }
        ],
    )
    body = _base_body()
    body["conversation_id"] = convo_id
    body["persona_slug"] = None
    res = _post(client, body)
    assert res.status_code == 403
