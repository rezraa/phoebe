# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Shared state and utilities for all Phoebe tools.

Every tool module imports from here to get access to the store and reasoner.
Dual-mode: conn=None uses standalone tome, conn provided uses Othrys graph.
"""

from __future__ import annotations

import json
from typing import Any

from phoebe.store import GraphStore
from phoebe.reasoning import Reasoner
from phoebe.tome import Tome
from phoebe.models import make_memory, make_source, make_entity, make_milestone

# ---------------------------------------------------------------------------
# Singletons — standalone mode (no conn)
# ---------------------------------------------------------------------------

_tome: Tome | None = None
_store: GraphStore | None = None
_reasoner: Reasoner | None = None


def get_store(conn: Any = None) -> GraphStore:
    """Return a GraphStore. If conn provided (Othrys mode), wraps that connection."""
    if conn is not None:
        return GraphStore(conn)
    global _tome, _store
    if _store is None:
        _tome = Tome()
        _tome.open()
        _store = GraphStore(_tome.connection())
    return _store


def get_reasoner(conn: Any = None) -> Reasoner:
    """Return a Reasoner. If conn provided (Othrys mode), wraps that connection."""
    if conn is not None:
        return Reasoner(conn)
    global _tome, _reasoner
    if _reasoner is None:
        get_store()  # ensures tome is open
        _reasoner = Reasoner(_tome.connection())
    return _reasoner


def coerce(val: Any, expected_type: type) -> Any:
    """Coerce JSON-encoded strings to native types (MCP client compat)."""
    if val is None:
        return None
    if isinstance(val, str) and expected_type in (list, dict):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, expected_type):
                return parsed
        except (ValueError, TypeError):
            pass
    return val
