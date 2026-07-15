# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Generate a context brief for a project and optional topic."""

from __future__ import annotations

from typing import Any

from phoebe.tools._shared import get_reasoner


def brief(
    project: str | None = None,
    topic: str | None = None,
    limit: int = 20,
    conn: Any = None,
) -> dict:
    """Generate a context brief for a project and optional topic.

    Body-store + id-list shape: ``memories`` is a map keyed by id (each a lean
    index record — derived title, NO content); each facet
    (recent_decisions, open_questions, unvalidated_assumptions,
    failed_approaches, topic_memories) is an ORDERED LIST OF IDS into it. Drill
    into a memory's full content with the ``get_memories`` tool.

    Args:
        project: Project name.
        topic: Optional topic to focus on.
        limit: Max results per facet.
        conn: Kuzu connection (Othrys mode) or None (standalone mode).

    Returns: {project, memories: {id: {...index...}}, recent_decisions: [id],
              open_questions: [id], unvalidated_assumptions: [id],
              failed_approaches: [id], topic_memories: [id], active_plans: [...],
              counts: {facet: n}}
    """
    reasoner = get_reasoner(conn)
    return reasoner.context_brief(project or "", topic=topic or None, limit=limit)
