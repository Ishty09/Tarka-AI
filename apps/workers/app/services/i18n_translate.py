"""Translate apps/web/messages/en.json into target locale bundles
(CLAUDE.md §27 step 53, §1.8).

The job is offline / on-demand: it's invoked from app/jobs/i18n_translate.py
either by hand or from a release script. Per locale we send one LLM call
containing the full set of keys to translate; this keeps round-trips
proportional to locales, not strings.

Default behaviour preserves any value that already exists in the target
file (so hand-curated translations from step 46 survive). Pass
`overwrite=True` to re-translate every key.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from app.prompts.i18n_translate import I18N_TRANSLATE_PROMPT
from app.services.llm import (
    QUARREL_ARGUE,
    LiteLLMClient,
    LiteLLMError,
    LiteLLMNetworkError,
    get_llm_client,
)

log = structlog.get_logger(__name__)


# Display names for the model prompt. Keep in sync with LOCALES in
# packages/shared/src/constants.ts (§4). Step 53 covers the top six
# launch locales (en + five targets); the remaining ten are present so
# the same job can backfill them post-launch without code edits.
LOCALE_NAMES: dict[str, str] = {
    "en": "English",
    "bn": "Bengali (Bangla)",
    "hi": "Hindi",
    "es": "Spanish (Latin American register)",
    "pt": "Portuguese (Brazilian register)",
    "ar": "Arabic (Modern Standard)",
    "it": "Italian",
    "ru": "Russian",
    "ko": "Korean",
    "ja": "Japanese",
    "de": "German",
    "fr": "French",
    "zh": "Mandarin Chinese (Simplified)",
    "id": "Indonesian",
    "vi": "Vietnamese",
    "he": "Hebrew",
}

# Top-six launch locales — the ones step 53 promises to fill. The job
# accepts arbitrary locale arguments; this is just the default target set.
DEFAULT_TARGETS: tuple[str, ...] = ("bn", "hi", "es", "pt", "ar")

SOURCE_LOCALE = "en"

# Placeholders we expect to see, e.g. {name}, {persona_name}. Currency
# anchors like ${stake} or `‏${stake}` (with RTL mark) still match because
# we scan only the {…} part.
_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


# ----- Errors ----------------------------------------------------------------


class TranslationError(Exception):
    """Raised when a locale's LLM output cannot be salvaged."""


# ----- Path resolution -------------------------------------------------------


def messages_dir(repo_root: Path | None = None) -> Path:
    """Resolve apps/web/messages from anywhere inside the repo.

    `repo_root` overrides the autodetected root — handy for tests.
    """

    if repo_root is not None:
        return repo_root / "apps" / "web" / "messages"

    here = Path(__file__).resolve()
    # apps/workers/app/services/i18n_translate.py → repo root is 4 parents up.
    root = here.parents[4]
    return root / "apps" / "web" / "messages"


def load_bundle(path: Path) -> dict[str, str]:
    """Read a locale bundle. Missing file → empty dict (treated as fresh)."""

    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise TranslationError(f"Bundle at {path} is not a JSON object")
    # Force str typing; an int slipping in would silently break next-intl.
    return {str(k): "" if v is None else str(v) for k, v in data.items()}


def write_bundle(path: Path, bundle: dict[str, str]) -> None:
    """Write a locale bundle. Sorted keys + trailing newline = stable diffs."""

    path.parent.mkdir(parents=True, exist_ok=True)
    serialised = json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True)
    path.write_text(serialised + "\n", encoding="utf-8")


# ----- Placeholder + shape validation ---------------------------------------


def extract_placeholders(value: str) -> set[str]:
    return set(_PLACEHOLDER_RE.findall(value))


def validate_translation(source: str, candidate: str) -> str | None:
    """Return None if the candidate is acceptable, else a reason string.

    A candidate is acceptable when the placeholder *set* matches the source.
    We don't enforce ordering (some languages reorder clauses) or count
    (a placeholder may repeat for emphasis), only that every name present in
    the source appears in the candidate and no foreign names sneak in.
    """

    src = extract_placeholders(source)
    cand = extract_placeholders(candidate)
    if src != cand:
        missing = src - cand
        extra = cand - src
        return f"placeholder mismatch (missing={sorted(missing)} extra={sorted(extra)})"
    if not candidate.strip() and source.strip():
        return "empty translation for non-empty source"
    return None


# ----- LLM call --------------------------------------------------------------


def _format_user_payload(target_locale: str, keys: dict[str, str]) -> str:
    language = LOCALE_NAMES.get(target_locale, target_locale)
    body = json.dumps(keys, ensure_ascii=False, indent=2, sort_keys=True)
    return (
        f"Target language: {language} (locale code: {target_locale}).\n"
        f"Source JSON:\n{body}"
    )


async def translate_keys(
    *,
    target_locale: str,
    source_keys: dict[str, str],
    client: LiteLLMClient | None = None,
) -> dict[str, str]:
    """Send one prompt for `source_keys`, return the translated dict.

    Raises TranslationError on LLM/JSON failure; the caller decides whether
    to keep partial results.
    """

    if not source_keys:
        return {}

    llm = client or get_llm_client()
    payload = _format_user_payload(target_locale, source_keys)

    try:
        response = await llm.chat(
            model=QUARREL_ARGUE,
            messages=[
                {"role": "system", "content": I18N_TRANSLATE_PROMPT},
                {"role": "user", "content": payload},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
            metadata={
                "generation_name": "i18n_translate",
                "tags": ["i18n", target_locale],
            },
        )
    except (LiteLLMError, LiteLLMNetworkError) as err:
        raise TranslationError(f"LLM call failed for {target_locale}: {err}") from err

    try:
        raw = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as err:
        raise TranslationError(f"Malformed LLM response for {target_locale}") from err

    if isinstance(raw, list):
        raw = "".join(
            block.get("text", "")
            for block in raw
            if isinstance(block, dict) and block.get("type") == "text"
        )
    if not isinstance(raw, str):
        raise TranslationError(f"Non-text content for {target_locale}")

    try:
        parsed: Any = json.loads(raw)
    except json.JSONDecodeError as err:
        raise TranslationError(
            f"LLM output for {target_locale} was not valid JSON: {err}"
        ) from err

    if not isinstance(parsed, dict):
        raise TranslationError(f"LLM output for {target_locale} is not an object")

    # The model occasionally wraps the result in an envelope like
    # {"translations": {...}} despite the prompt. Unwrap once if the only
    # value is a nested dict whose keys overlap with our source keys.
    if len(parsed) == 1:
        only_value = next(iter(parsed.values()))
        if isinstance(only_value, dict) and set(only_value.keys()) & set(source_keys):
            parsed = only_value

    return {str(k): "" if v is None else str(v) for k, v in parsed.items()}


# ----- Orchestration ---------------------------------------------------------


@dataclass(slots=True)
class LocaleResult:
    locale: str
    translated: int = 0
    skipped: int = 0
    fell_back_to_source: int = 0
    missing_keys: list[str] = field(default_factory=list)
    rejected_keys: list[tuple[str, str]] = field(default_factory=list)
    wrote_path: Path | None = None


def _select_keys_to_translate(
    source: dict[str, str],
    target: dict[str, str],
    overwrite: bool,
) -> dict[str, str]:
    if overwrite:
        return dict(source)
    return {k: v for k, v in source.items() if k not in target or not target[k]}


def _merge(
    *,
    source: dict[str, str],
    existing: dict[str, str],
    translated: dict[str, str],
    result: LocaleResult,
) -> dict[str, str]:
    merged: dict[str, str] = {}
    for key, src_value in source.items():
        if key in translated:
            candidate = translated[key]
            reason = validate_translation(src_value, candidate)
            if reason is None:
                merged[key] = candidate
                result.translated += 1
            else:
                result.rejected_keys.append((key, reason))
                # Prefer keeping the existing value over the source if both
                # exist; otherwise fall back to source so the bundle stays
                # functional even with placeholder drift.
                fallback = existing.get(key) or src_value
                merged[key] = fallback
                if fallback == src_value:
                    result.fell_back_to_source += 1
        elif existing_value := existing.get(key):
            merged[key] = existing_value
            result.skipped += 1
        else:
            merged[key] = src_value
            result.fell_back_to_source += 1
            result.missing_keys.append(key)
    return merged


async def translate_locale(
    *,
    target_locale: str,
    source: dict[str, str],
    existing: dict[str, str],
    overwrite: bool = False,
    client: LiteLLMClient | None = None,
) -> tuple[dict[str, str], LocaleResult]:
    """Translate `source` into `target_locale` and merge with `existing`.

    Returns the merged bundle and a LocaleResult with per-key accounting.
    """

    if target_locale == SOURCE_LOCALE:
        raise ValueError("Cannot translate the source locale into itself")
    if target_locale not in LOCALE_NAMES:
        raise ValueError(f"Unknown target locale: {target_locale}")

    result = LocaleResult(locale=target_locale)
    to_translate = _select_keys_to_translate(source, existing, overwrite)
    if not to_translate:
        log.info("i18n.translate.nothing_to_do", locale=target_locale)
        result.skipped = len(source)
        return dict(existing), result

    translated = await translate_keys(
        target_locale=target_locale,
        source_keys=to_translate,
        client=client,
    )
    # Account for skips happening before the model call.
    result.skipped = len(source) - len(to_translate)
    merged = _merge(
        source=source,
        existing=existing,
        translated=translated,
        result=result,
    )
    return merged, result


async def run(
    *,
    targets: tuple[str, ...] = DEFAULT_TARGETS,
    overwrite: bool = False,
    dry_run: bool = False,
    repo_root: Path | None = None,
    client: LiteLLMClient | None = None,
) -> list[LocaleResult]:
    """Top-level entry point used by the CLI job.

    `dry_run` skips disk writes but still performs the LLM call so the
    operator can see what would change.
    """

    root_dir = messages_dir(repo_root)
    source_path = root_dir / f"{SOURCE_LOCALE}.json"
    source = load_bundle(source_path)
    if not source:
        raise TranslationError(f"Source bundle missing or empty: {source_path}")

    results: list[LocaleResult] = []
    for locale in targets:
        target_path = root_dir / f"{locale}.json"
        existing = load_bundle(target_path)
        merged, result = await translate_locale(
            target_locale=locale,
            source=source,
            existing=existing,
            overwrite=overwrite,
            client=client,
        )
        if not dry_run:
            write_bundle(target_path, merged)
            result.wrote_path = target_path
        log.info(
            "i18n.translate.locale_done",
            locale=locale,
            translated=result.translated,
            skipped=result.skipped,
            fell_back_to_source=result.fell_back_to_source,
            rejected=len(result.rejected_keys),
            dry_run=dry_run,
        )
        results.append(result)
    return results
