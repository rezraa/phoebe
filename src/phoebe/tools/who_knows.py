# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Who has the most expertise on a topic?"""

from __future__ import annotations

from typing import Any

from phoebe.tools._shared import get_reasoner


def who_knows(
    topic: str,
    limit: int = 5,
    conn: Any = None,
) -> dict:
    """Who has the most expertise on a topic?

    Args:
        topic: Entity name to check expertise for.
        limit: Max results.
        conn: Kuzu connection (Othrys mode) or None (standalone mode).

    Returns: {topic, experts: [{person, memory_count}]}
    """
    reasoner = get_reasoner(conn)
    experts = reasoner.who_knows(topic, limit)
    return {"topic": topic, "experts": experts}
