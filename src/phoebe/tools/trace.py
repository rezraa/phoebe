# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Walk causal chains — why did this happen? What did it cause?"""

from __future__ import annotations

from typing import Any

from phoebe.tools._shared import get_reasoner


def trace(
    memory_id: str,
    direction: str = "causes",
    max_depth: int = 5,
    conn: Any = None,
) -> dict:
    """Walk causal chains — why did this happen? What did it cause?

    Args:
        memory_id: The memory to trace from.
        direction: "causes" (backwards to root cause) or "effects" (forward).
        max_depth: Maximum chain depth.
        conn: Kuzu connection (Othrys mode) or None (standalone mode).

    Returns: {memory_id, direction, chain, depth, current, superseded_by}
    """
    reasoner = get_reasoner(conn)

    if direction == "effects":
        chain = reasoner.trace_effects(memory_id, max_depth)
    else:
        chain = reasoner.trace_causes(memory_id, max_depth)

    currency = reasoner.is_current(memory_id)

    return {
        "memory_id": memory_id,
        "direction": direction,
        "chain": chain,
        "depth": len(chain),
        "current": currency["current"],
        "superseded_by": currency.get("superseded_by"),
    }
