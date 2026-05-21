"""Sentry init + scrubber tests (§27 step 60).

The init path is exercised in two modes: DSN empty (skip) and DSN set
(returns True). The before_send scrubber is the part we actually care
about — it has to strip credentials and PII before anything leaves the
process.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from app.config import Settings
from app.observability import _before_send, init_sentry


@pytest.fixture
def base_settings() -> Settings:
    return Settings(
        NEXT_PUBLIC_APP_URL="https://quarrel.test",
        LITELLM_PROXY_URL="https://litellm.test",
        LITELLM_MASTER_KEY="x",
        NEXT_PUBLIC_SUPABASE_URL="https://supabase.test",
        SUPABASE_SERVICE_ROLE_KEY="x",
        NEXT_PUBLIC_SUPABASE_ANON_KEY="x",
    )


def test_init_skips_when_dsn_blank(
    monkeypatch: pytest.MonkeyPatch,
    base_settings: Settings,
) -> None:
    import app.observability as obs

    monkeypatch.setattr(obs, "get_settings", lambda: base_settings)
    assert init_sentry() is False


def test_init_initialises_when_dsn_set(
    monkeypatch: pytest.MonkeyPatch,
    base_settings: Settings,
) -> None:
    import app.observability as obs

    captured: dict[str, Any] = {}

    def fake_init(**kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(obs.sentry_sdk, "init", fake_init)
    settings_with_dsn = base_settings.model_copy(
        update={"sentry_dsn": "https://abc@sentry.io/123"}
    )
    monkeypatch.setattr(obs, "get_settings", lambda: settings_with_dsn)

    assert init_sentry() is True
    assert captured["dsn"] == "https://abc@sentry.io/123"
    assert captured["send_default_pii"] is False
    assert captured["before_send"] is obs._before_send


def test_scrubber_redacts_authorization_and_cookie_headers() -> None:
    event = cast(
        Any,
        {
            "request": {
                "headers": {
                    "Authorization": "Bearer secret",
                    "Cookie": "sb-access-token=abc",
                    "X-Api-Key": "litellm-secret",
                    "User-Agent": "test",
                },
            },
        },
    )
    result = _before_send(event, {})
    headers = result["request"]["headers"]  # type: ignore[index]
    assert headers["Authorization"] == "[REDACTED]"
    assert headers["Cookie"] == "[REDACTED]"
    assert headers["X-Api-Key"] == "[REDACTED]"
    # Non-secret headers survive.
    assert headers["User-Agent"] == "test"


def test_scrubber_drops_request_body_keys() -> None:
    event = cast(
        Any,
        {
            "request": {
                "headers": {},
                "data": {"prompt": "very private user prompt"},
                "json": {"some": "json"},
                "form": "form-encoded body",
            }
        },
    )
    result = _before_send(event, {})
    req = result["request"]  # type: ignore[index]
    assert "data" not in req
    assert "json" not in req
    assert "form" not in req


def test_scrubber_strips_pii_from_user_block() -> None:
    event = cast(
        Any,
        {
            "user": {
                "id": "user-uuid",
                "email": "leak@example.com",
                "ip_address": "1.2.3.4",
                "username": "alice",
            }
        },
    )
    result = _before_send(event, {})
    user = result["user"]  # type: ignore[index]
    assert user["id"] == "user-uuid"
    assert "email" not in user
    assert "ip_address" not in user
    assert "username" not in user


def test_scrubber_handles_missing_request_block() -> None:
    # Sentry sometimes ships events without a request — must not crash.
    event = cast(Any, {"message": "boom"})
    result = _before_send(event, {})
    assert result == {"message": "boom"}


def test_scrubber_substring_match_catches_supabase_keys() -> None:
    event = cast(
        Any,
        {
            "request": {
                "headers": {
                    "X-Supabase-Service-Role": "shouldnt-leak",
                    "X-OpenAI-Authorization": "shouldnt-leak",
                },
            },
        },
    )
    result = _before_send(event, {})
    headers = result["request"]["headers"]  # type: ignore[index]
    assert headers["X-Supabase-Service-Role"] == "[REDACTED]"
    assert headers["X-OpenAI-Authorization"] == "[REDACTED]"
