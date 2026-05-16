"""Async LiteLLM client.

Python counterpart of packages/ai. Every LLM call in apps/workers routes
through here (§1 rule 4). We don't import the OpenAI or Anthropic SDKs — the
proxy is OpenAI-shape, and httpx is enough.
"""

from __future__ import annotations

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
        response_format: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
        user: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Non-streaming chat completion. Returns the parsed JSON body."""

        body: dict[str, Any] = {"model": model, "messages": messages}
        if temperature is not None:
            body["temperature"] = temperature
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
