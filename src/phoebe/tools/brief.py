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

    Returns recent decisions, open questions, failed approaches,
    unvalidated assumptions, and topic-specific memories.

    Args:
        project: Project name.
        topic: Optional topic to focus on.
        limit: Max results per category.
        conn: Kuzu connection (Othrys mode) or None (standalone mode).

    Returns: {project, recent_decisions, open_questions, failed_approaches,
              unvalidated_assumptions, topic_memories}
    """
    reasoner = get_reasoner(conn)
    return reasoner.context_brief(project or "", topic=topic or None, limit=limit)
