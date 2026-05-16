"""Internal helpers for narrowing supabase-py response shapes.

supabase-py types .data as `int | float | Sequence[JSON] | Mapping[str, JSON]`
which is too loose for our callsites. We always know the concrete shape from
the table being queried, so these helpers `cast` at the boundary instead of
sprinkling `cast(...)` at every call.
"""

from __future__ import annotations

from typing import Any, cast


def row_or_none(data: Any) -> dict[str, Any] | None:
    """Narrow `.maybe_single().execute().data` to a row dict, or None."""

    if data is None:
        return None
    return cast(dict[str, Any], data)


def rows(data: Any) -> list[dict[str, Any]]:
    """Narrow `.execute().data` to a list of row dicts."""

    if data is None:
        return []
    return cast(list[dict[str, Any]], data)
