"""Email service: template rendering + send pipeline."""

from __future__ import annotations

import os
from typing import Any

import httpx
import pytest

# Configure required env BEFORE importing the email module so get_settings()
# (lru_cache) sees the test values.
os.environ.setdefault("NEXT_PUBLIC_APP_URL", "https://quarrel.test")
os.environ.setdefault("LITELLM_PROXY_URL", "https://litellm.test")
os.environ.setdefault("LITELLM_MASTER_KEY", "test")
os.environ.setdefault("NEXT_PUBLIC_SUPABASE_URL", "https://supabase.test")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test")
os.environ.setdefault("NEXT_PUBLIC_SUPABASE_ANON_KEY", "test")

from app.services import email as email_mod
from app.services.email import (
    TEMPLATES,
    SendResult,
    render,
    send_email,
)

# ----- Fakes ---------------------------------------------------------------


class _Res:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Q:
    def __init__(self, table: _Table, op: str, payload: Any = None) -> None:
        self._t = table
        self._op = op
        self._payload = payload
        self._filters: list[tuple[str, Any]] = []
        self._maybe_single = False

    def select(self, _cols: str = "*") -> _Q:
        return self

    def eq(self, col: str, val: Any) -> _Q:
        self._filters.append((col, val))
        return self

    def maybe_single(self) -> _Q:
        self._maybe_single = True
        return self

    async def execute(self) -> _Res:
        if self._op == "select":
            rows = [r for r in self._t.rows if all(r.get(c) == v for c, v in self._filters)]
            if self._maybe_single:
                return _Res(rows[0] if rows else None)
            return _Res(rows)
        if self._op == "insert":
            payloads = self._payload if isinstance(self._payload, list) else [self._payload]
            for p in payloads:
                self._t.rows.append(dict(p))
            return _Res(payloads)
        raise AssertionError(self._op)


class _Table:
    def __init__(self, name: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []

    def select(self, _cols: str = "*") -> _Q:
        return _Q(self, "select")

    def insert(self, payload: Any) -> _Q:
        return _Q(self, "insert", payload)


class FakeSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, _Table] = {"idempotency_keys": _Table("idempotency_keys")}

    def table(self, name: str) -> _Table:
        if name not in self.tables:
            self.tables[name] = _Table(name)
        return self.tables[name]


# ----- Sample variables for each template -----------------------------------


SAMPLE_VARS: dict[str, dict[str, Any]] = {
    "welcome": {"display_name": "Rabbi"},
    "magic_link": {"magic_link": "https://quarrel.test/auth/cb?t=abc", "ttl_minutes": 15},
    "subscription_confirmed": {
        "tier": "pro",
        "current_period_end": "2026-06-19",
        "amount_formatted": "$9.99",
        "interval": "month",
    },
    "subscription_canceled": {"tier": "pro", "access_until": "2026-06-19"},
    "payment_failed": {
        "amount_formatted": "$9.99",
        "tier": "pro",
        "grace_until": "2026-05-26",
        "manage_url": "https://polar.test/manage",
    },
    "wager_won": {
        "goal": "Run 5x per week for 6 weeks",
        "stake_formatted": "$50.00",
        "wager_id": "w-1",
    },
    "wager_lost": {
        "goal": "Run 5x per week for 6 weeks",
        "stake_formatted": "$50.00",
        "anti_charity_name": "Heritage Foundation",
        "wager_id": "w-1",
    },
    "couples_invite": {
        "inviter_name": "Aisha",
        "accept_url": "https://quarrel.test/couples/accept?code=xyz",
        "expires_at": "2026-05-26",
    },
    "data_export_ready": {
        "download_url": "https://quarrel.test/exports/abc",
        "ttl_hours": 24,
    },
    "account_deletion_grace_started": {"delete_on": "2026-06-18"},
    "emergency_contact_notification": {"user_display_name": "Rabbi"},
    "mirror_report_ready": {"week_label": "May 12"},
    "eulogy_ready": {"quarter": 2},
    "moderation_rejection": {
        "entity_type": "persona",
        "entity_label": "south_park_dad",
        "reason": "Real-person impersonation isn't allowed in the marketplace.",
    },
    "beta_invite": {
        "signup_url": "https://quarrel.ai/onboarding?token=abc",
    },
}


# ----- Tests ---------------------------------------------------------------


@pytest.mark.parametrize("name", list(TEMPLATES.keys()))
def test_render_each_template(name: str) -> None:
    vars_ = SAMPLE_VARS[name]
    out = render(name, vars_)  # type: ignore[arg-type]
    assert out.subject
    assert "<!doctype html>" in out.html
    assert out.text.strip()


def test_render_missing_var_raises() -> None:
    from jinja2 import UndefinedError

    with pytest.raises(UndefinedError):
        render("welcome", {})  # missing display_name


def test_transactional_footer_omits_unsubscribe() -> None:
    out = render("welcome", SAMPLE_VARS["welcome"])
    assert "Unsubscribe" not in out.html
    assert "Unsubscribe" not in out.text


def test_marketing_footer_includes_unsubscribe() -> None:
    out = render("mirror_report_ready", SAMPLE_VARS["mirror_report_ready"])
    assert "Unsubscribe" in out.html
    assert "Unsubscribe" in out.text or "Unsubscribe:" in out.text


@pytest.mark.asyncio
async def test_dry_run_when_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # The lru_cache on get_settings means our os.environ default
    # `RESEND_API_KEY=""` already produced an empty key for the cached
    # settings — patch the settings function for clarity.
    from app.config import Settings

    class _S(Settings):
        pass

    fake_settings = _S(
        NEXT_PUBLIC_APP_URL="https://quarrel.test",
        LITELLM_PROXY_URL="https://litellm.test",
        LITELLM_MASTER_KEY="x",
        NEXT_PUBLIC_SUPABASE_URL="https://supabase.test",
        SUPABASE_SERVICE_ROLE_KEY="x",
        NEXT_PUBLIC_SUPABASE_ANON_KEY="x",
        RESEND_API_KEY="",
    )
    monkeypatch.setattr(email_mod, "get_settings", lambda: fake_settings)

    sb = FakeSupabase()
    result = await send_email(
        template="welcome",
        to_email="rabbi@example.com",
        variables=SAMPLE_VARS["welcome"],
        idempotency_key="welcome:rabbi-1",
        supabase=sb,  # type: ignore[arg-type]
    )
    assert result.status == "dry_run"
    # Idempotency row recorded so a retry would be skipped.
    assert len(sb.tables["idempotency_keys"].rows) == 1


@pytest.mark.asyncio
async def test_idempotent_second_send_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import Settings

    fake_settings = Settings(
        NEXT_PUBLIC_APP_URL="https://quarrel.test",
        LITELLM_PROXY_URL="https://litellm.test",
        LITELLM_MASTER_KEY="x",
        NEXT_PUBLIC_SUPABASE_URL="https://supabase.test",
        SUPABASE_SERVICE_ROLE_KEY="x",
        NEXT_PUBLIC_SUPABASE_ANON_KEY="x",
        RESEND_API_KEY="",
    )
    monkeypatch.setattr(email_mod, "get_settings", lambda: fake_settings)

    sb = FakeSupabase()
    # Pre-seed an idempotency_keys row to simulate a prior send.
    sb.tables["idempotency_keys"].rows.append(
        {"key": "welcome:rabbi-1", "scope": "email:welcome"}
    )

    result = await send_email(
        template="welcome",
        to_email="rabbi@example.com",
        variables=SAMPLE_VARS["welcome"],
        idempotency_key="welcome:rabbi-1",
        supabase=sb,  # type: ignore[arg-type]
    )
    assert result.status == "skipped"
    assert result.reason == "idempotent"


@pytest.mark.asyncio
async def test_send_calls_resend_when_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import Settings

    fake_settings = Settings(
        NEXT_PUBLIC_APP_URL="https://quarrel.test",
        LITELLM_PROXY_URL="https://litellm.test",
        LITELLM_MASTER_KEY="x",
        NEXT_PUBLIC_SUPABASE_URL="https://supabase.test",
        SUPABASE_SERVICE_ROLE_KEY="x",
        NEXT_PUBLIC_SUPABASE_ANON_KEY="x",
        RESEND_API_KEY="re_live_test",
    )
    monkeypatch.setattr(email_mod, "get_settings", lambda: fake_settings)

    captured: dict[str, Any] = {}

    class _Resp:
        status_code = 200
        content = b'{"id":"em_1"}'

        def json(self) -> dict[str, Any]:
            return {"id": "em_1"}

    class _Client:
        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]) -> _Resp:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _Resp()

        async def aclose(self) -> None:  # pragma: no cover - not used here
            return None

    sb = FakeSupabase()
    result = await send_email(
        template="welcome",
        to_email="rabbi@example.com",
        to_name="Rabbi",
        variables=SAMPLE_VARS["welcome"],
        supabase=sb,  # type: ignore[arg-type]
        client=_Client(),  # type: ignore[arg-type]
    )

    assert isinstance(result, SendResult)
    assert result.status == "sent"
    assert result.message_id == "em_1"
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"]["authorization"] == "Bearer re_live_test"
    assert captured["json"]["to"] == ["Rabbi <rabbi@example.com>"]
    assert "Welcome" in captured["json"]["subject"]


@pytest.mark.asyncio
async def test_send_failure_status(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import Settings

    fake_settings = Settings(
        NEXT_PUBLIC_APP_URL="https://quarrel.test",
        LITELLM_PROXY_URL="https://litellm.test",
        LITELLM_MASTER_KEY="x",
        NEXT_PUBLIC_SUPABASE_URL="https://supabase.test",
        SUPABASE_SERVICE_ROLE_KEY="x",
        NEXT_PUBLIC_SUPABASE_ANON_KEY="x",
        RESEND_API_KEY="re_live_test",
    )
    monkeypatch.setattr(email_mod, "get_settings", lambda: fake_settings)

    class _Resp:
        status_code = 503
        content = b'{"error":"upstream"}'

        def json(self) -> dict[str, Any]:
            return {"error": "upstream"}

    class _Client:
        async def post(
            self, url: str, *, headers: dict[str, str], json: dict[str, Any]
        ) -> _Resp:
            return _Resp()

        async def aclose(self) -> None:  # pragma: no cover
            return None

    sb = FakeSupabase()
    result = await send_email(
        template="welcome",
        to_email="rabbi@example.com",
        variables=SAMPLE_VARS["welcome"],
        supabase=sb,  # type: ignore[arg-type]
        client=_Client(),  # type: ignore[arg-type]
    )
    assert result.status == "failed"
    assert result.reason == "resend_503"


@pytest.mark.asyncio
async def test_send_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import Settings

    fake_settings = Settings(
        NEXT_PUBLIC_APP_URL="https://quarrel.test",
        LITELLM_PROXY_URL="https://litellm.test",
        LITELLM_MASTER_KEY="x",
        NEXT_PUBLIC_SUPABASE_URL="https://supabase.test",
        SUPABASE_SERVICE_ROLE_KEY="x",
        NEXT_PUBLIC_SUPABASE_ANON_KEY="x",
        RESEND_API_KEY="re_live_test",
    )
    monkeypatch.setattr(email_mod, "get_settings", lambda: fake_settings)

    class _Client:
        async def post(self, *_a: Any, **_k: Any) -> Any:
            raise httpx.ConnectError("boom")

        async def aclose(self) -> None:  # pragma: no cover
            return None

    sb = FakeSupabase()
    result = await send_email(
        template="welcome",
        to_email="rabbi@example.com",
        variables=SAMPLE_VARS["welcome"],
        supabase=sb,  # type: ignore[arg-type]
        client=_Client(),  # type: ignore[arg-type]
    )
    assert result.status == "failed"
    assert result.reason == "network"
