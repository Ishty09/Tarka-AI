"""Async LiteLLM client.

Python counterpart of packages/ai. Every LLM call in apps/workers routes
through here (§1 rule 4). We don't import the OpenAI or Anthropic SDKs — the
proxy is OpenAI-shape, and httpx is enough.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from app.config import Settings, get_settings

log = structlog.get_logger(__name__)


# ----- Model names mirror packages/ai/src/models.ts (§7.1) -------------------

QUARREL_ARGUE = "quarrel-argue"
QUARREL_CHEAP = "quarrel-cheap"
QUARREL_EMBED = "quarrel-embed"


# ----- Errors ----------------------------------------------------------------


class LiteLLMError(Exception):
    """Non-2xx response from the proxy."""

    def __init__(self, message: str, status: int, body: Any) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class LiteLLMNetworkError(Exception):
    """Connection / timeout / TLS failure reaching the proxy."""


# ----- Client ----------------------------------------------------------------


class LiteLLMClient:
    """Thin wrapper around the LiteLLM proxy.

    Stateless aside from the underlying httpx client; safe to share across
    requests. Construct via `get_llm_client()` to reuse the singleton.
    """

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(
            base_url=str(settings.litellm_proxy_url).rstrip("/"),
            timeout=settings.litellm_timeout_seconds,
            headers={
                "authorization": f"Bearer {settings.litellm_master_key}",
                "content-type": "application/json",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
        user: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Non-streaming chat completion. Returns the parsed JSON body."""

        body: dict[str, Any] = {"model": model, "messages": messages}
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if response_format is not None:
            body["response_format"] = response_format
        if metadata is not None:
            body["metadata"] = metadata
        if user is not None:
            body["user"] = user

        headers: dict[str, str] = {}
        if idempotency_key is not None:
            headers["idempotency-key"] = idempotency_key

        try:
            res = await self._client.post("/chat/completions", json=body, headers=headers)
        except httpx.HTTPError as err:
            raise LiteLLMNetworkError(str(err)) from err

        if res.status_code >= 400:
            try:
                err_body = res.json()
            except ValueError:
                err_body = res.text
            log.warning(
                "litellm.error",
                status=res.status_code,
                model=model,
                body=err_body,
            )
            raise LiteLLMError(
                f"LiteLLM /chat/completions {res.status_code}",
                res.status_code,
                err_body,
            )

        data: dict[str, Any] = res.json()
        return data

    async def embed(
        self,
        *,
        model: str,
        input: str | list[str],
        user: str | None = None,
    ) -> list[list[float]]:
        """Embeddings call. Returns a list of vectors in input order.

        Single str input → list with one vector. List input → list with one
        vector per item. We hide the OpenAI envelope (`data: [{embedding}]`)
        because every caller wants the bare floats.
        """

        body: dict[str, Any] = {"model": model, "input": input}
        if user is not None:
            body["user"] = user

        try:
            res = await self._client.post("/embeddings", json=body)
        except httpx.HTTPError as err:
            raise LiteLLMNetworkError(str(err)) from err

        if res.status_code >= 400:
            try:
                err_body = res.json()
            except ValueError:
                err_body = res.text
            log.warning(
                "litellm.embed_error",
                status=res.status_code,
                model=model,
                body=err_body,
            )
            raise LiteLLMError(
                f"LiteLLM /embeddings {res.status_code}",
                res.status_code,
                err_body,
            )

        data: dict[str, Any] = res.json()
        items = data.get("data", [])
        return [item["embedding"] for item in items]

    async def chat_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float | None = None,
        metadata: dict[str, Any] | None = None,
        user: str | None = None,
        idempotency_key: str | None = None,
    ) -> AsyncIterator[ChatStreamDelta]:
        """Streaming chat completion. Yields ChatStreamDelta per SSE chunk.

        Mirrors the chatStream async iterator in packages/ai/src/client.ts —
        consumers in chat routes adapt these to whatever SSE protocol they
        emit downstream.
        """

        body: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
        if temperature is not None:
            body["temperature"] = temperature
        if metadata is not None:
            body["metadata"] = metadata
        if user is not None:
            body["user"] = user

        headers: dict[str, str] = {}
        if idempotency_key is not None:
            headers["idempotency-key"] = idempotency_key

        try:
            req = self._client.build_request("POST", "/chat/completions", json=body, headers=headers)
            res = await self._client.send(req, stream=True)
        except httpx.HTTPError as err:
            raise LiteLLMNetworkError(str(err)) from err

        try:
            if res.status_code >= 400:
                err_text = await res.aread()
                try:
                    err_body: Any = json.loads(err_text)
                except ValueError:
                    err_body = err_text.decode("utf-8", errors="replace")
                log.warning(
                    "litellm.stream_error",
                    status=res.status_code,
                    model=model,
                    body=err_body,
                )
                raise LiteLLMError(
                    f"LiteLLM /chat/completions {res.status_code}",
                    res.status_code,
                    err_body,
                )

            buffer = ""
            async for chunk in res.aiter_text():
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line.removeprefix("data:").strip()
                    if payload == "[DONE]":
                        return
                    try:
                        decoded = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    delta = _to_stream_delta(decoded)
                    if delta is not None:
                        yield delta
        finally:
            await res.aclose()


@dataclass(slots=True)
class ChatStreamDelta:
    """One streaming chunk from chat_stream."""

    delta: str
    finish_reason: str | None
    cached_tokens: int | None
    raw: dict[str, Any]


def _to_stream_delta(chunk: dict[str, Any]) -> ChatStreamDelta | None:
    choices = chunk.get("choices") or []
    if not choices:
        # Some chunks (e.g. usage trailer) have no choices but carry totals.
        usage = chunk.get("usage")
        if isinstance(usage, dict):
            cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
            return ChatStreamDelta(delta="", finish_reason=None, cached_tokens=cached, raw=chunk)
        return None

    first = choices[0]
    delta_obj = first.get("delta") or {}
    text = delta_obj.get("content") or ""
    finish = first.get("finish_reason")
    usage = chunk.get("usage") or {}
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")

    if not text and finish is None and cached is None:
        return None
    return ChatStreamDelta(delta=text, finish_reason=finish, cached_tokens=cached, raw=chunk)


_singleton: LiteLLMClient | None = None


def get_llm_client() -> LiteLLMClient:
    """Lazy singleton. FastAPI tests can monkeypatch this for isolation."""

    global _singleton
    if _singleton is None:
        _singleton = LiteLLMClient(get_settings())
    return _singleton


def set_llm_client(client: LiteLLMClient | None) -> None:
    """Test hook: substitute or clear the cached client."""

    global _singleton
    _singleton = client
