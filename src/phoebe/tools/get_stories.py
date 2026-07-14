# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Batched drill-down read for specific stories — the heavy-field companion
to the lean ``get_plan`` tree.

``get_plan`` returns a lean tree (ids, names, statuses, descriptions,
acceptance criteria — NO transcripts). To read a completed story's actual
work product, collect its id and call ``get_stories``: ``input_context`` and
``output`` come back whole, and ``full_output`` (the raw Titan transcript)
only when ``include_full_output`` is set.
"""

from __future__ import annotations

from typing import Any, Union

from phoebe.tools._shared import get_store, coerce_str_or_container

# Agreed batch cap (council a46da9f5): refuse an oversize id list rather than
# fan out an unbounded IN-clause.
_MAX_STORY_IDS = 50


def _dedup_ids(story_ids: Any) -> list[str]:
    """Normalise the id argument to a deduped, first-seen-order list of
    non-empty strings.

    Tolerates the three shapes an MCP caller can send: a native list, a bare
    id string, or a JSON-encoded list string. Non-string / empty members are
    dropped; genuine ids that simply do not resolve are surfaced in
    ``missing`` by the caller, never silently swallowed here.
    """
    raw = coerce_str_or_container(story_ids, list)
    if isinstance(raw, str):
        items: list = [raw]
    elif isinstance(raw, list):
        items = raw
    else:
        items = []

    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not isinstance(item, str) or not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def get_stories(
    story_ids: Union[list[str], str, None],
    include_full_output: bool = False,
    project: str | None = None,
    conn: Any = None,
) -> dict:
    """Fetch heavy fields for specific stories by id (the ``get_plan`` drill-down).

    ``get_plan`` returns a lean tree with NO story transcripts. Pass the ids
    you need here to read their work product.

    Args:
        story_ids: Story ids to fetch. Accepts a list, a bare id string, or a
            JSON-encoded list string. Deduped (first-seen order); capped at 50
            per call.
        include_full_output: When True, also return each story's ``full_output``
            (the raw Titan transcript). Omitted from the result entirely
            otherwise — the transcript is never read unless asked for.
        project: Bound project for defense-in-depth scoping (injected by the
            Othrys server). When set, only stories whose plan.project matches
            byte-exact are returned; an id owned by another project falls to
            ``missing``. None (standalone) = no scoping.
        conn: Kuzu connection (Othrys mode) or None (standalone).

    Returns:
        {
          "stories": [
            {id, name, status, phase, assigned_titan, sequence,
             input_context, output, [full_output]}
          ],
          "missing": [requested ids that did not resolve (or were denied by
                      project scope)]
        }
        ``input_context`` and ``output`` are returned WHOLE (never truncated).
        On an oversize list:
        {"error", "error_type": "too_many_ids", "limit": 50, "requested": N}.
    """
    if isinstance(include_full_output, str):
        include_full_output = include_full_output.strip().lower() in ("true", "1", "yes")

    ids = _dedup_ids(story_ids)
    if not ids:
        return {"stories": [], "missing": []}
    if len(ids) > _MAX_STORY_IDS:
        return {
            "error": (
                f"Too many story ids: {len(ids)} requested, max "
                f"{_MAX_STORY_IDS} per call. Split into batches."
            ),
            "error_type": "too_many_ids",
            "limit": _MAX_STORY_IDS,
            "requested": len(ids),
        }

    store = get_store(conn)
    rows = store.get_stories(
        ids,
        include_full_output=include_full_output,
        project=project or None,
    )
    found = {row["id"] for row in rows}
    missing = [sid for sid in ids if sid not in found]
    return {"stories": rows, "missing": missing}
