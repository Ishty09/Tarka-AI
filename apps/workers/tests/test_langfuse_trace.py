"""Trace metadata helper tests (§27 step 62)."""

from __future__ import annotations

from app.services.langfuse_trace import build_metadata


def test_minimum_payload_only_name_set() -> None:
    md = build_metadata(name="eulogy")
    assert md == {"generation_name": "eulogy"}


def test_all_known_fields_present() -> None:
    md = build_metadata(
        name="argue.devils_advocate",
        user_id="u1",
        session_id="conv-1",
        mode="argue",
        persona_slug="devils_advocate",
        tier="pro",
        locale="en",
    )
    assert md["generation_name"] == "argue.devils_advocate"
    assert md["trace_user_id"] == "u1"
    assert md["session_id"] == "conv-1"
    assert md["tags"] == ["argue", "devils_advocate", "pro", "en"]


def test_tags_filter_drops_missing_fields() -> None:
    # Only persona_slug + tier present — tags shouldn't carry empty slots.
    md = build_metadata(
        name="steelman",
        user_id="u1",
        persona_slug="the_skeptic",
        tier="max",
    )
    assert md["tags"] == ["the_skeptic", "max"]


def test_tags_omitted_entirely_when_nothing_to_tag() -> None:
    md = build_metadata(name="solo", user_id="u1")
    assert "tags" not in md


def test_extra_merges_at_top_level_and_drops_none() -> None:
    md = build_metadata(
        name="contradiction.judge",
        extra={"cached_tokens": 0, "fallback_used": False, "model_used": "gpt-5"},
    )
    assert md["cached_tokens"] == 0
    assert md["fallback_used"] is False
    assert md["model_used"] == "gpt-5"


def test_extra_drops_none_values() -> None:
    md = build_metadata(
        name="fact_extraction",
        extra={"cached_tokens": None, "fallback_used": None, "kind": "real"},
    )
    assert "cached_tokens" not in md
    assert "fallback_used" not in md
    assert md["kind"] == "real"


def test_user_id_and_session_id_omitted_when_empty() -> None:
    md = build_metadata(name="x", user_id="", session_id="")
    assert "trace_user_id" not in md
    assert "session_id" not in md
