"""i18n translation service tests (§27 step 53).

Covers the value-shaping helpers, the per-locale merge logic, and the
top-level `run` orchestration with a stubbed LLM client.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.services import i18n_translate as svc
from app.services.i18n_translate import (
    LocaleResult,
    TranslationError,
    _merge,
    _select_keys_to_translate,
    extract_placeholders,
    load_bundle,
    run,
    translate_keys,
    translate_locale,
    validate_translation,
    write_bundle,
)
from app.services.llm import LiteLLMError

# ----- Stub client ----------------------------------------------------------


class FakeLLM:
    def __init__(self, responses: dict[str, str] | Exception) -> None:
        self._responses = responses
        self.calls: list[dict[str, Any]] = []

    async def chat(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if isinstance(self._responses, Exception):
            raise self._responses
        # The payload encodes the locale on the first line; pick the matching
        # translation body for whichever locale is being translated.
        payload = kwargs["messages"][1]["content"]
        locale = payload.split("locale code: ", 1)[1].split(")", 1)[0]
        content = self._responses.get(locale, "{}")
        return {"choices": [{"message": {"role": "assistant", "content": content}}]}


# ----- Placeholder helpers --------------------------------------------------


def test_extract_placeholders_finds_named_slots() -> None:
    assert extract_placeholders("Hello {name}, you owe {amount}") == {"name", "amount"}


def test_extract_placeholders_ignores_dollar_prefix() -> None:
    # ${stake} → only {stake} is a placeholder; the $ stays literal.
    assert extract_placeholders("You lose ${stake}.") == {"stake"}


def test_validate_translation_passes_on_matching_placeholders() -> None:
    assert validate_translation("Hi {name}", "ওহে {name}") is None


def test_validate_translation_flags_missing_placeholder() -> None:
    reason = validate_translation("Hi {name}", "ওহে")
    assert reason is not None
    assert "missing" in reason


def test_validate_translation_flags_extra_placeholder() -> None:
    reason = validate_translation("Hi", "Hi {name}")
    assert reason is not None
    assert "extra" in reason


def test_validate_translation_rejects_empty_translation_of_nonempty_source() -> None:
    assert validate_translation("hello", "   ") == "empty translation for non-empty source"


# ----- Bundle I/O -----------------------------------------------------------


def test_load_bundle_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_bundle(tmp_path / "nope.json") == {}


def test_load_bundle_rejects_non_object(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(TranslationError):
        load_bundle(path)


def test_write_bundle_sorts_keys_and_trails_newline(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    write_bundle(path, {"b": "two", "a": "one"})
    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    # Sorted order matters for stable git diffs.
    assert text.index('"a"') < text.index('"b"')


# ----- Key selection --------------------------------------------------------


def test_select_keys_default_skips_existing_translations() -> None:
    source = {"a": "Apple", "b": "Banana"}
    target = {"a": "Manzana"}  # b is missing
    selected = _select_keys_to_translate(source, target, overwrite=False)
    assert selected == {"b": "Banana"}


def test_select_keys_overwrite_returns_full_source() -> None:
    source = {"a": "Apple", "b": "Banana"}
    target = {"a": "Manzana"}
    selected = _select_keys_to_translate(source, target, overwrite=True)
    assert selected == source


def test_select_keys_treats_empty_existing_as_missing() -> None:
    source = {"a": "Apple"}
    target = {"a": ""}
    assert _select_keys_to_translate(source, target, overwrite=False) == {"a": "Apple"}


# ----- Merge logic ----------------------------------------------------------


def test_merge_keeps_valid_translation() -> None:
    result = LocaleResult(locale="bn")
    merged = _merge(
        source={"a": "Hi {name}"},
        existing={},
        translated={"a": "ওহে {name}"},
        result=result,
    )
    assert merged == {"a": "ওহে {name}"}
    assert result.translated == 1
    assert result.rejected_keys == []


def test_merge_falls_back_to_existing_when_placeholder_mismatches() -> None:
    result = LocaleResult(locale="bn")
    merged = _merge(
        source={"a": "Hi {name}"},
        existing={"a": "Existing translation"},
        translated={"a": "Bad translation no placeholder"},
        result=result,
    )
    assert merged == {"a": "Existing translation"}
    assert len(result.rejected_keys) == 1
    assert result.fell_back_to_source == 0


def test_merge_falls_back_to_source_when_existing_absent() -> None:
    result = LocaleResult(locale="bn")
    merged = _merge(
        source={"a": "Hi {name}"},
        existing={},
        translated={"a": "Bad"},
        result=result,
    )
    assert merged == {"a": "Hi {name}"}
    assert result.fell_back_to_source == 1


def test_merge_keeps_existing_when_translation_absent() -> None:
    result = LocaleResult(locale="bn")
    merged = _merge(
        source={"a": "Hi"},
        existing={"a": "প্রিয়"},
        translated={},
        result=result,
    )
    assert merged == {"a": "প্রিয়"}
    assert result.skipped == 1


def test_merge_records_missing_key_when_neither_source_target_have_translation() -> None:
    result = LocaleResult(locale="bn")
    merged = _merge(
        source={"a": "Only source"},
        existing={},
        translated={},
        result=result,
    )
    assert merged == {"a": "Only source"}
    assert result.missing_keys == ["a"]
    assert result.fell_back_to_source == 1


# ----- LLM call -------------------------------------------------------------


@pytest.mark.asyncio
async def test_translate_keys_parses_json_object() -> None:
    fake = FakeLLM({"bn": json.dumps({"a": "ক"})})
    out = await translate_keys(
        target_locale="bn",
        source_keys={"a": "Apple"},
        client=fake,  # type: ignore[arg-type]
    )
    assert out == {"a": "ক"}
    assert fake.calls[0]["model"] == "quarrel-argue"
    assert fake.calls[0]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_translate_keys_unwraps_translations_envelope() -> None:
    # Model occasionally wraps output as {"translations": {...}} despite
    # the prompt; the service should unwrap it.
    fake = FakeLLM({"bn": json.dumps({"translations": {"a": "ক"}})})
    out = await translate_keys(
        target_locale="bn",
        source_keys={"a": "Apple"},
        client=fake,  # type: ignore[arg-type]
    )
    assert out == {"a": "ক"}


@pytest.mark.asyncio
async def test_translate_keys_raises_on_non_json_output() -> None:
    fake = FakeLLM({"bn": "definitely not json"})
    with pytest.raises(TranslationError):
        await translate_keys(
            target_locale="bn",
            source_keys={"a": "Apple"},
            client=fake,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_translate_keys_raises_on_litellm_error() -> None:
    fake = FakeLLM(LiteLLMError("boom", 500, None))
    with pytest.raises(TranslationError):
        await translate_keys(
            target_locale="bn",
            source_keys={"a": "Apple"},
            client=fake,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_translate_keys_short_circuits_empty_input() -> None:
    fake = FakeLLM({})
    out = await translate_keys(
        target_locale="bn",
        source_keys={},
        client=fake,  # type: ignore[arg-type]
    )
    assert out == {}
    assert fake.calls == []


# ----- Locale-level orchestration ------------------------------------------


@pytest.mark.asyncio
async def test_translate_locale_rejects_source_locale() -> None:
    with pytest.raises(ValueError, match="source locale"):
        await translate_locale(
            target_locale="en",
            source={"a": "Apple"},
            existing={},
        )


@pytest.mark.asyncio
async def test_translate_locale_rejects_unknown_locale() -> None:
    with pytest.raises(ValueError, match="Unknown target locale"):
        await translate_locale(
            target_locale="xx",
            source={"a": "Apple"},
            existing={},
        )


@pytest.mark.asyncio
async def test_translate_locale_skips_when_target_already_complete() -> None:
    fake = FakeLLM({})  # would 404 if called
    merged, result = await translate_locale(
        target_locale="bn",
        source={"a": "Apple"},
        existing={"a": "ক"},
        client=fake,  # type: ignore[arg-type]
    )
    assert merged == {"a": "ক"}
    assert result.translated == 0
    assert fake.calls == []


@pytest.mark.asyncio
async def test_translate_locale_overwrite_replaces_existing() -> None:
    fake = FakeLLM({"bn": json.dumps({"a": "নতুন"})})
    merged, result = await translate_locale(
        target_locale="bn",
        source={"a": "Apple"},
        existing={"a": "পুরাতন"},
        overwrite=True,
        client=fake,  # type: ignore[arg-type]
    )
    assert merged == {"a": "নতুন"}
    assert result.translated == 1


# ----- Top-level run --------------------------------------------------------


def _write_source(repo_root: Path, payload: dict[str, str]) -> None:
    p = repo_root / "apps" / "web" / "messages"
    p.mkdir(parents=True, exist_ok=True)
    (p / "en.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.asyncio
async def test_run_writes_each_target_locale(tmp_path: Path) -> None:
    _write_source(tmp_path, {"a": "Apple", "b": "Boom {name}"})
    fake = FakeLLM(
        {
            "bn": json.dumps({"a": "ক", "b": "বুম {name}"}),
            "hi": json.dumps({"a": "सेब", "b": "बूम {name}"}),
        }
    )

    results = await run(
        targets=("bn", "hi"),
        repo_root=tmp_path,
        client=fake,  # type: ignore[arg-type]
    )

    assert {r.locale for r in results} == {"bn", "hi"}
    bn_payload = json.loads((tmp_path / "apps/web/messages/bn.json").read_text(encoding="utf-8"))
    assert bn_payload == {"a": "ক", "b": "বুম {name}"}
    hi_payload = json.loads((tmp_path / "apps/web/messages/hi.json").read_text(encoding="utf-8"))
    assert hi_payload == {"a": "सेब", "b": "बूम {name}"}


@pytest.mark.asyncio
async def test_run_dry_run_does_not_write(tmp_path: Path) -> None:
    _write_source(tmp_path, {"a": "Apple"})
    fake = FakeLLM({"bn": json.dumps({"a": "ক"})})

    await run(
        targets=("bn",),
        repo_root=tmp_path,
        client=fake,  # type: ignore[arg-type]
        dry_run=True,
    )

    assert not (tmp_path / "apps/web/messages/bn.json").exists()


@pytest.mark.asyncio
async def test_run_raises_when_source_bundle_missing(tmp_path: Path) -> None:
    (tmp_path / "apps" / "web" / "messages").mkdir(parents=True)
    fake = FakeLLM({})
    with pytest.raises(TranslationError):
        await run(
            targets=("bn",),
            repo_root=tmp_path,
            client=fake,  # type: ignore[arg-type]
        )


# ----- Sanity: defaults stay in sync with constants.ts ----------------------


def test_default_targets_match_top_six_minus_source() -> None:
    # If this ever drifts, update either constants.ts or DEFAULT_TARGETS.
    assert svc.SOURCE_LOCALE == "en"
    assert svc.DEFAULT_TARGETS == ("bn", "hi", "es", "pt", "ar")
    for code in (svc.SOURCE_LOCALE, *svc.DEFAULT_TARGETS):
        assert code in svc.LOCALE_NAMES
