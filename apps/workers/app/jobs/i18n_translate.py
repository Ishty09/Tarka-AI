"""i18n translation job entry point (CLAUDE.md §27 step 53).

Designed to be invoked by hand from a release script:

    uv run python -m app.jobs.i18n_translate
    uv run python -m app.jobs.i18n_translate --target bn,hi
    uv run python -m app.jobs.i18n_translate --overwrite --dry-run

The actual work lives in services.i18n_translate.run — this module is the
argparse front door + structured-log summary. The job is intentionally
out-of-band (no FastAPI route, no cron) because translations land on the
release branch, not in production traffic.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import structlog

from app.services.i18n_translate import (
    DEFAULT_TARGETS,
    LOCALE_NAMES,
    SOURCE_LOCALE,
    LocaleResult,
    TranslationError,
    run,
)

log = structlog.get_logger(__name__)


def _parse_targets(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return DEFAULT_TARGETS
    locales = tuple(part.strip() for part in raw.split(",") if part.strip())
    bad = [code for code in locales if code == SOURCE_LOCALE or code not in LOCALE_NAMES]
    if bad:
        raise SystemExit(
            f"Unknown / unsupported target locale(s): {bad}. "
            f"Valid: {sorted(c for c in LOCALE_NAMES if c != SOURCE_LOCALE)}"
        )
    return locales


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="i18n_translate",
        description="Translate apps/web/messages/en.json into target locale bundles.",
    )
    parser.add_argument(
        "--target",
        help=(
            "Comma-separated locale codes (e.g. bn,hi,es,pt,ar). "
            "Defaults to the launch-six minus en."
        ),
        default=None,
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-translate keys that already have a value in the target bundle.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the LLM calls but skip writing locale files to disk.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Override repo root (for tests/CI). Defaults to autodetect.",
    )
    return parser


def _summarise(results: list[LocaleResult], *, dry_run: bool) -> int:
    """Pretty-print a summary; return process exit code."""

    rejected_total = sum(len(r.rejected_keys) for r in results)
    fallback_total = sum(r.fell_back_to_source for r in results)

    print()
    print(f"{'locale':<6} {'translated':>10} {'skipped':>8} {'fallback':>9} {'rejected':>9}")
    print("-" * 50)
    for r in results:
        print(
            f"{r.locale:<6} {r.translated:>10} {r.skipped:>8} "
            f"{r.fell_back_to_source:>9} {len(r.rejected_keys):>9}"
        )
    print()
    if dry_run:
        print("(dry-run — no files written)")
    else:
        for r in results:
            if r.wrote_path is not None:
                print(f"wrote {r.wrote_path}")

    for r in results:
        for key, reason in r.rejected_keys:
            log.warning(
                "i18n.translate.rejected",
                locale=r.locale,
                key=key,
                reason=reason,
            )

    # Exit non-zero if anything was rejected or had to fall back — operators
    # should review before merging the generated bundle.
    return 1 if (rejected_total or fallback_total) else 0


async def _main_async(args: argparse.Namespace) -> int:
    targets = _parse_targets(args.target)
    try:
        results = await run(
            targets=targets,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
            repo_root=args.repo_root,
        )
    except TranslationError as err:
        log.error("i18n.translate.failed", error=str(err))
        print(f"error: {err}", file=sys.stderr)
        return 2
    return _summarise(results, dry_run=args.dry_run)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return asyncio.run(_main_async(args))


if __name__ == "__main__":  # pragma: no cover — CLI entry
    raise SystemExit(main())
