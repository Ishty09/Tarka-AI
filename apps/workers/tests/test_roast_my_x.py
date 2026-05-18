"""Roast My X service tests."""

from __future__ import annotations

from typing import Any

import pytest

from app.services.llm import LiteLLMError, LiteLLMNetworkError
from app.services.roast_my_x import (
    MAX_ROAST_CHARS,
    MIN_ROAST_CHARS,
    ROAST_TARGETS,
    RoastMyXRun,
    UnknownTargetError,
    generate_roast,
    is_known_target,
    persist_roast_my_x_run,
    run_roast_my_x,
    target_label,
)


HOST_SLUG = "devils_advocate"
GOOD_ROAST = (
    "Your headline is four buzzwords and a verb. The verb is 'leveraging'. "
    "Pick one thing you actually did, not three identities you're trying on."
)


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

    def select(self, _cols: str = "*") -> "_Query":
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, val))
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


# ----- target table integrity ----------------------------------------------


def test_roast_targets_has_twenty_entries() -> None:
    assert len(ROAST_TARGETS) == 20
    # Spot-check a couple key slugs.
    assert "linkedin" in ROAST_TARGETS
    assert "wedding-speech" in ROAST_TARGETS


def test_is_known_target_filters() -> None:
    assert is_known_target("linkedin") is True
    assert is_known_target("not_a_real_target") is False


def test_target_label_falls_back_to_slug_humanised() -> None:
    assert target_label("linkedin") == "LinkedIn profile"
    # Unknown — humanise dashes.
    assert target_label("self-driving-car") == "self driving car"


# ----- generate_roast ------------------------------------------------------


async def test_generate_returns_text_for_known_target() -> None:
    llm = FakeLLM(content=GOOD_ROAST)
    out = await generate_roast(
        target="linkedin",
        content="Senior PM | Driving innovation",
        client=llm,  # type: ignore[arg-type]
    )
    assert out is not None
    assert "headline" in out.lower()


async def test_generate_unknown_target_raises() -> None:
    llm = FakeLLM(content=GOOD_ROAST)
    with pytest.raises(UnknownTargetError):
        await generate_roast(
            target="ghost",
            content="x" * 30,
            client=llm,  # type: ignore[arg-type]
        )


async def test_generate_strips_surrounding_quotes() -> None:
    quoted = f'"{GOOD_ROAST}"'
    llm = FakeLLM(content=quoted)
    out = await generate_roast(
        target="linkedin",
        content="x" * 30,
        client=llm,  # type: ignore[arg-type]
    )
    assert out is not None
    assert not out.startswith('"')
    assert not out.endswith('"')


async def test_generate_too_short_returns_none() -> None:
    short = "Brief."
    assert len(short) < MIN_ROAST_CHARS
    llm = FakeLLM(content=short)
    assert (
        await generate_roast(
            target="linkedin",
            content="x" * 30,
            client=llm,  # type: ignore[arg-type]
        )
    ) is None


async def test_generate_truncates_to_max() -> None:
    over = "x" * (MAX_ROAST_CHARS + 200)
    llm = FakeLLM(content=over)
    out = await generate_roast(
        target="linkedin",
        content="x" * 30,
        client=llm,  # type: ignore[arg-type]
    )
    assert out is not None
    assert len(out) <= MAX_ROAST_CHARS


async def test_generate_network_error_returns_none() -> None:
    llm = FakeLLM(exc=LiteLLMNetworkError("down"))
    assert (
        await generate_roast(
            target="linkedin",
            content="x" * 30,
            client=llm,  # type: ignore[arg-type]
        )
    ) is None


async def test_generate_http_error_returns_none() -> None:
    llm = FakeLLM(exc=LiteLLMError("500", 500, "x"))
    assert (
        await generate_roast(
            target="linkedin",
            content="x" * 30,
            client=llm,  # type: ignore[arg-type]
        )
    ) is None


# ----- persist + run -------------------------------------------------------


async def test_persist_writes_conversation_and_messages_with_target_metadata() -> None:
    sb = FakeSupabase()
    sb.seed_host()
    run = await persist_roast_my_x_run(
        sb,  # type: ignore[arg-type]
        user_id="u",
        run=RoastMyXRun(
            target="linkedin",
            content="LinkedIn copy",
            roast=GOOD_ROAST,
        ),
    )
    convo = sb.table("conversations").rows[0]
    assert convo["mode"] == "roast_my_x"
    assert convo["metadata"]["target"] == "linkedin"
    assert convo["title"].lower().startswith("roast my linkedin")

    messages = sb.table("messages").rows
    assert len(messages) == 2
    assert messages[0]["metadata"]["kind"] == "roast_my_x_content"
    assert messages[1]["metadata"]["kind"] == "roast_my_x_roast"
    assert run.conversation_id is not None
    assert run.assistant_message_id == messages[1]["id"]


async def test_run_end_to_end_happy() -> None:
    sb = FakeSupabase()
    sb.seed_host()
    llm = FakeLLM(content=GOOD_ROAST)
    run = await run_roast_my_x(
        sb,  # type: ignore[arg-type]
        user_id="u",
        target="linkedin",
        content="Senior PM | Driving innovation | passionate about AI",
        client=llm,  # type: ignore[arg-type]
    )
    assert run is not None
    assert run.target == "linkedin"
    assert len(sb.table("messages").rows) == 2


async def test_run_llm_failure_yields_none() -> None:
    sb = FakeSupabase()
    sb.seed_host()
    llm = FakeLLM(exc=LiteLLMNetworkError("down"))
    run = await run_roast_my_x(
        sb,  # type: ignore[arg-type]
        user_id="u",
        target="linkedin",
        content="x" * 50,
        client=llm,  # type: ignore[arg-type]
    )
    assert run is None
    assert "conversations" not in sb.tables or sb.tables["conversations"].rows == []
