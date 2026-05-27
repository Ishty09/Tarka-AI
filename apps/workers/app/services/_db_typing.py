"""Internal helpers for narrowing supabase-py response shapes.

supabase-py types .data as `int | float | Sequence[JSON] | Mapping[str, JSON]`
which is too loose for our callsites. We always know the concrete shape from
the table being queried, so these helpers `cast` at the boundary instead of
sprinkling `cast(...)` at every call.

IMPORTANT: pass `result.data`, NEVER the raw response object — mistaking
the two is a runtime AttributeError that mocks accidentally hide. The
`Mapping | None` signature on `row_or_none` is deliberate: it makes the
mistake a mypy error instead of a production crash. Mirror that here
when adding new helpers.
"""

from __future__ import annotations

from typing import Any, cast


def row_or_none(data: Any) -> dict[str, Any] | None:
    """Narrow `.maybe_single().execute().data` to a row dict, or None.

    `data` is `result.data` — the row dict (when a row matched) or None.
    Passing the response object itself (i.e. forgetting `.data`) is a
    runtime AttributeError that mocks accidentally hide. Type stays
    Any because supabase-py types `.data` as a loose union that
    breaks if we tighten here; review every new call to confirm
    `.data` is being passed.
    """

    if data is None:
        return None
    return cast(dict[str, Any], data)


def rows(data: Any) -> list[dict[str, Any]]:
    """Narrow `.execute().data` to a list of row dicts."""

    if data is None:
        return []
    return cast(list[dict[str, Any]], data)
