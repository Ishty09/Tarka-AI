"""Push notification rendering + delivery pipeline."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("NEXT_PUBLIC_APP_URL", "https://quarrel.test")
os.environ.setdefault("LITELLM_PROXY_URL", "https://litellm.test")
os.environ.setdefault("LITELLM_MASTER_KEY", "test")
os.environ.setdefault("NEXT_PUBLIC_SUPABASE_URL", "https://supabase.test")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test")
os.environ.setdefault("NEXT_PUBLIC_SUPABASE_ANON_KEY", "test")

from app.services.notification_prefs import (
    NOTIFICATION_CATEGORIES,
    PUSH_TEMPLATE_CATEGORY,
)
from app.services.push import (
    PUSH_TEMPLATES,
    DeliveryResult,
    MissingTemplateError,
    PushPayload,
    PushSubscriptionRow,
    PushTemplate,
    deliver_to_user,
    messages,
    render_push,
    supported_locales,
)

# ----- Helpers --------------------------------------------------------------


@pytest.fixture
def messages_root() -> Path:
    # apps/web/messages — resolved relative to this file's repo location.
    here = Path(__file__).resolve()
    # tests -> workers -> apps -> repo
    repo = here.parents[3]
    return repo / "apps" / "web" / "messages"


# ----- Locale loading -------------------------------------------------------


def test_every_push_template_has_a_category() -> None:
    """Every entry in PUSH_TEMPLATES must map to a known category so the
    settings-page toggles cover the full push surface. Drift here means
    a user mutes a category but still gets the push.
    """

    for template in PUSH_TEMPLATES:
        assert template in PUSH_TEMPLATE_CATEGORY, f"{template} missing category"
        assert PUSH_TEMPLATE_CATEGORY[template] in NOTIFICATION_CATEGORIES


def test_categories_match_shared_ts_list() -> None:
    """packages/shared/src/constants.ts is the source of truth for the
    UI; this Python list must mirror it. Read the TS file and compare.
    """

    here = Path(__file__).resolve()
    repo = here.parents[3]
    ts_path = repo / "packages" / "shared" / "src" / "constants.ts"
    text = ts_path.read_text(encoding="utf-8")
    # Grab the array literal between `NOTIFICATION_CATEGORIES = [` and
    # the closing `]`. No JSON parser needed; it's a static list.
    start = text.index("NOTIFICATION_CATEGORIES = [")
    end = text.index("]", start)
    fragment = text[start:end]
    ts_keys = {
        line.strip().strip(",").strip('"').strip("'")
        for line in fragment.splitlines()[1:]
        if line.strip() and not line.strip().startswith("//")
    }
    assert ts_keys == set(NOTIFICATION_CATEGORIES)


def test_loads_all_launch_locales(messages_root: Path) -> None:
    locales = supported_locales(messages_root)
    # We seed at least these in step 45.
    for required in ("en", "bn", "hi", "es", "pt", "ar"):
        assert required in locales, f"missing locale {required}"


@pytest.mark.parametrize("template", list(PUSH_TEMPLATES))
def test_every_launch_locale_has_each_template(template: PushTemplate, messages_root: Path) -> None:
    title_key = f"push.{template}.title"
    body_key = f"push.{template}.body"
    for locale in ("en", "bn", "hi", "es", "pt", "ar"):
        data = messages(messages_root)[locale]
        assert title_key in data, f"{locale} missing {title_key}"
        assert body_key in data, f"{locale} missing {body_key}"


# ----- Render ---------------------------------------------------------------


def test_render_substitutes_variables(messages_root: Path) -> None:
    out = render_push(
        "daily_roast",
        locale="en",
        variables={"persona_name": "Bengali Mama", "roast_preview": "you again"},
        root=messages_root,
    )
    assert "Bengali Mama" in out.title
    assert "you again" in out.body


def test_render_falls_back_to_en_for_unknown_locale(
    messages_root: Path, caplog: pytest.LogCaptureFixture
) -> None:
    out = render_push(
        "daily_roast",
        locale="xx",
        variables={"persona_name": "Devil's Advocate", "roast_preview": "?"},
        root=messages_root,
    )
    assert "Devil's Advocate" in out.title


def test_render_attaches_deep_link(messages_root: Path) -> None:
    out = render_push(
        "mirror_ready",
        locale="en",
        variables={},
        deep_link="/mirror",
        root=messages_root,
    )
    assert out.data["url"] == "/mirror"
    assert out.data["template"] == "mirror_ready"


def test_render_missing_var_raises(messages_root: Path) -> None:
    with pytest.raises(MissingTemplateError):
        render_push(
            "wager_checkin",
            locale="en",
            variables={"wager_goal": "Lift 3x/wk"},  # missing 'stake'
            root=messages_root,
        )


def test_render_unknown_template_raises(tmp_path: Path) -> None:
    # Build a stub messages dir that has en but missing one template key.
    (tmp_path / "en.json").write_text(
        json.dumps({"push.daily_roast.title": "ok", "push.daily_roast.body": "ok"}),
        encoding="utf-8",
    )
    with pytest.raises(MissingTemplateError):
        render_push(
            "mirror_ready",
            locale="en",
            variables={},
            root=tmp_path,
        )


# ----- Delivery -------------------------------------------------------------


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
        self.tables: dict[str, _Table] = {}

    def table(self, name: str) -> _Table:
        self.tables.setdefault(name, _Table(name))
        return self.tables[name]


class RecordingWebSender:
    def __init__(self) -> None:
        self.calls: list[tuple[PushSubscriptionRow, PushPayload]] = []

    async def send(
        self, *, subscription: PushSubscriptionRow, payload: PushPayload
    ) -> DeliveryResult:
        self.calls.append((subscription, payload))
        return DeliveryResult(subscription_id=subscription.id, status="sent")


class RecordingExpoSender:
    def __init__(self) -> None:
        self.calls: list[tuple[PushSubscriptionRow, PushPayload]] = []

    async def send(
        self, *, subscription: PushSubscriptionRow, payload: PushPayload
    ) -> DeliveryResult:
        self.calls.append((subscription, payload))
        return DeliveryResult(subscription_id=subscription.id, status="sent")


@pytest.mark.asyncio
async def test_deliver_routes_per_platform(messages_root: Path) -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.append(
        {"id": "u1", "locale": "en", "notification_push": True}
    )
    sb.table("push_subscriptions").rows.extend(
        [
            {"id": "s-web", "user_id": "u1", "platform": "web", "token": "w-tok"},
            {"id": "s-ios", "user_id": "u1", "platform": "ios", "token": "i-tok"},
            {"id": "s-and", "user_id": "u1", "platform": "android", "token": "a-tok"},
        ]
    )

    web = RecordingWebSender()
    expo = RecordingExpoSender()

    results = await deliver_to_user(
        user_id="u1",
        template="mirror_ready",
        variables={},
        supabase=sb,  # type: ignore[arg-type]
        web_sender=web,
        expo_sender=expo,
    )

    assert len(results) == 3
    assert {r.status for r in results} == {"sent"}
    assert len(web.calls) == 1
    assert len(expo.calls) == 2  # ios + android


@pytest.mark.asyncio
async def test_deliver_respects_mute(messages_root: Path) -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.append(
        {"id": "u1", "locale": "en", "notification_push": False}
    )
    sb.table("push_subscriptions").rows.append(
        {"id": "s-web", "user_id": "u1", "platform": "web", "token": "w-tok"}
    )

    web = RecordingWebSender()
    expo = RecordingExpoSender()
    results = await deliver_to_user(
        user_id="u1",
        template="mirror_ready",
        variables={},
        supabase=sb,  # type: ignore[arg-type]
        web_sender=web,
        expo_sender=expo,
    )
    assert results == []
    assert web.calls == []
    assert expo.calls == []


@pytest.mark.asyncio
async def test_deliver_respects_per_category_mute(messages_root: Path) -> None:
    """User globally allows push but mutes the 'couples' category — a
    couples_dispute_created push should be suppressed while a mirror_ready
    push to the same user goes through.
    """

    sb = FakeSupabase()
    sb.table("profiles").rows.append(
        {
            "id": "u1",
            "locale": "en",
            "notification_push": True,
            "notification_preferences": {"push": {"couples": False}},
        }
    )
    sb.table("push_subscriptions").rows.append(
        {"id": "s-web", "user_id": "u1", "platform": "web", "token": "w-tok"}
    )

    web = RecordingWebSender()
    expo = RecordingExpoSender()

    muted = await deliver_to_user(
        user_id="u1",
        template="couples_dispute_created",
        variables={"sender_name": "A", "dispute_title": "x"},
        supabase=sb,  # type: ignore[arg-type]
        web_sender=web,
        expo_sender=expo,
    )
    assert muted == []
    assert web.calls == []

    allowed = await deliver_to_user(
        user_id="u1",
        template="mirror_ready",
        variables={},
        supabase=sb,  # type: ignore[arg-type]
        web_sender=web,
        expo_sender=expo,
    )
    assert len(allowed) == 1
    assert allowed[0].status == "sent"


@pytest.mark.asyncio
async def test_deliver_idempotent(messages_root: Path) -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.append(
        {"id": "u1", "locale": "en", "notification_push": True}
    )
    sb.table("push_subscriptions").rows.append(
        {"id": "s-web", "user_id": "u1", "platform": "web", "token": "w-tok"}
    )
    # Pre-seed an idempotency_keys row so the second call short-circuits.
    sb.table("idempotency_keys").rows.append(
        {"key": "mirror:u1:2026-W20", "scope": "push:mirror_ready"}
    )

    web = RecordingWebSender()
    expo = RecordingExpoSender()
    results = await deliver_to_user(
        user_id="u1",
        template="mirror_ready",
        variables={},
        idempotency_key="mirror:u1:2026-W20",
        supabase=sb,  # type: ignore[arg-type]
        web_sender=web,
        expo_sender=expo,
    )

    assert results == []
    assert web.calls == []


@pytest.mark.asyncio
async def test_deliver_writes_idempotency_on_success(messages_root: Path) -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.append(
        {"id": "u1", "locale": "en", "notification_push": True}
    )
    sb.table("push_subscriptions").rows.append(
        {"id": "s-web", "user_id": "u1", "platform": "web", "token": "w-tok"}
    )

    web = RecordingWebSender()
    expo = RecordingExpoSender()
    results = await deliver_to_user(
        user_id="u1",
        template="contradiction",
        variables={"summary": "Two weeks ago you said X."},
        idempotency_key="contradiction:u1:42",
        supabase=sb,  # type: ignore[arg-type]
        web_sender=web,
        expo_sender=expo,
    )

    assert [r.status for r in results] == ["sent"]
    idem = sb.tables["idempotency_keys"].rows
    assert len(idem) == 1
    assert idem[0]["key"] == "contradiction:u1:42"
    assert idem[0]["scope"] == "push:contradiction"


@pytest.mark.asyncio
async def test_deliver_no_subscriptions_returns_empty(messages_root: Path) -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.append(
        {"id": "u1", "locale": "en", "notification_push": True}
    )
    results = await deliver_to_user(
        user_id="u1",
        template="mirror_ready",
        variables={},
        supabase=sb,  # type: ignore[arg-type]
        web_sender=RecordingWebSender(),
        expo_sender=RecordingExpoSender(),
    )
    assert results == []


@pytest.mark.asyncio
async def test_deliver_uses_user_locale(messages_root: Path) -> None:
    sb = FakeSupabase()
    sb.table("profiles").rows.append(
        {"id": "u1", "locale": "bn", "notification_push": True}
    )
    sb.table("push_subscriptions").rows.append(
        {"id": "s-and", "user_id": "u1", "platform": "android", "token": "tok"}
    )

    expo = RecordingExpoSender()
    web = RecordingWebSender()
    await deliver_to_user(
        user_id="u1",
        template="mirror_ready",
        variables={},
        supabase=sb,  # type: ignore[arg-type]
        web_sender=web,
        expo_sender=expo,
    )

    assert len(expo.calls) == 1
    _, payload = expo.calls[0]
    # bn.json: "তোমার Mirror Report তৈরি।"
    assert "Mirror Report" in payload.title
    assert "তোমার" in payload.title
