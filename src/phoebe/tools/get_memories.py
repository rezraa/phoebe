# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Batched drill-down read for specific memories — the detail-tier companion
to the lean index that ``context_brief`` / ``brief`` return.

``brief`` returns lean INDEX records (id, derived title, type, status, ... —
NO content). To read a memory's full content, collect its id and call
``get_memories``: ``content`` comes back decoded and WHOLE.
"""

from __future__ import annotations

from typing import Any, Union

from phoebe.store import memory_detail_record
from phoebe.tools._shared import get_store, _dedup_ids

# Agreed batch cap (mirrors get_stories): refuse an oversize id list rather
# than fan out an unbounded IN-clause.
_MAX_MEMORY_IDS = 50


def get_memories(
    memory_ids: Union[list[str], str, None],
    project: str | None = None,
    conn: Any = None,
) -> dict:
    """Fetch full detail for specific memories by id (the brief drill-down).

    ``brief`` / ``context_brief`` return lean index records with NO content.
    Pass the ids you need here to read their full content.

    Args:
        memory_ids: Memory ids to fetch. Accepts a list, a bare id string, or a
            JSON-encoded list string. Deduped (first-seen order); capped at 50
            per call.
        project: Bound project for defense-in-depth scoping (injected by the
            Othrys server). When set, only memories whose ``project`` matches
            byte-exact are returned; an id owned by another project falls to
            ``missing``. None (standalone) = no scoping.
        conn: Kuzu connection (Othrys mode) or None (standalone).

    Returns:
        {
          "memories": [
            {id, title, memory_type, status, outcome, agent, project,
             confidence, timestamp, content}  # content decoded WHOLE
          ],
          "missing": [requested ids that did not resolve (or were denied by
                      project scope)]
        }
        ``content`` is returned WHOLE (never truncated). On an oversize list:
        {"error", "error_type": "too_many_ids", "limit": 50, "requested": N}.
    """
    ids = _dedup_ids(memory_ids)
    if not ids:
        return {"memories": [], "missing": []}
    if len(ids) > _MAX_MEMORY_IDS:
        return {
            "error": (
                f"Too many memory ids: {len(ids)} requested, max "
                f"{_MAX_MEMORY_IDS} per call. Split into batches."
            ),
            "error_type": "too_many_ids",
            "limit": _MAX_MEMORY_IDS,
            "requested": len(ids),
        }

    store = get_store(conn)
    rows = store.get_memories(ids, project=project or None)
    found = {row["id"] for row in rows}
    missing = [mid for mid in ids if mid not in found]
    memories = [memory_detail_record(row) for row in rows]
    return {"memories": memories, "missing": missing}
