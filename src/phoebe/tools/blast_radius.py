# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""What depends on this entity? What's the impact of changing it?"""

from __future__ import annotations

from typing import Any

from phoebe.tools._shared import get_reasoner


def blast_radius(
    entity_name: str,
    conn: Any = None,
) -> dict:
    """What depends on this entity? What's the impact of changing it?

    Args:
        entity_name: Name of the system/service/component to analyze.
        conn: Kuzu connection (Othrys mode) or None (standalone mode).

    Returns: {entity, dependents, dependent_count, recent_changes}
    """
    reasoner = get_reasoner(conn)
    return reasoner.blast_radius(entity_name)
