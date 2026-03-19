# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Return tome statistics — node counts and stale source report."""

from __future__ import annotations

from typing import Any

from phoebe.tools._shared import get_store, get_reasoner


def stats(conn: Any = None) -> dict:
    """Return tome statistics — node counts and stale source report.

    Args:
        conn: Kuzu connection (Othrys mode) or None (standalone mode).

    Returns: {memories, sources, entities, milestones, stale_sources, stale_count}
    """
    store = get_store(conn)
    reasoner = get_reasoner(conn)

    # Count nodes
    counts = {}
    for table in ("memories", "sources", "entities", "milestones"):
        try:
            if conn:
                result = conn.execute(f"MATCH (n:{table}) RETURN COUNT(n) AS c")
            else:
                result = store._conn.execute(f"MATCH (n:{table}) RETURN COUNT(n) AS c")
            row = result.get_next()
            counts[table] = row[0] if row else 0
        except Exception:
            counts[table] = 0

    stale = reasoner.stale_source_impact()

    return {
        **counts,
        "stale_sources": stale,
        "stale_count": len(stale),
    }
