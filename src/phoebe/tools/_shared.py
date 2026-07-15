# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Shared state and utilities for all Phoebe tools.

Every tool module imports from here to get access to the store and reasoner.
Dual-mode: conn=None uses standalone tome, conn provided uses Othrys graph.
"""

from __future__ import annotations

import functools
import json
import logging
from typing import Any, Callable

from phoebe.store import GraphStore
from phoebe.reasoning import Reasoner
from phoebe.tome import Tome
from phoebe.models import make_memory, make_source, make_entity, make_milestone

_log = logging.getLogger(__name__)

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


def coerce(val: Any, expected_type: type | None = None, default: Any = None) -> Any:
    """Coerce MCP-supplied values to a native type, else return *default*.

    MCP clients sometimes send JSON containers as strings. This decodes a
    str into the expected list/dict when possible. On any irreconcilable
    type mismatch the *default* is returned, so callers never receive a
    truthy wrong-type value that survives ``coerce(...) or {}`` and crashes
    a later ``.get()``.
    """
    if val is None:
        return default
    if isinstance(val, str) and expected_type in (list, dict):
        try:
            parsed = json.loads(val)
        except (ValueError, TypeError):
            return default
        return parsed if isinstance(parsed, expected_type) else default
    if expected_type is not None and not isinstance(val, expected_type):
        return default
    return val


def coerce_or_raise(
    val: Any, expected_type: type, empty_default: Any
) -> Any:
    """Like :func:`coerce`, but for values that get PERSISTED.

    ``coerce`` returns its default on any irreconcilable mismatch, which is
    correct for transient/optional fields but dangerous for a field that is
    then written to storage: a non-empty wrong-type value (e.g. a dict where
    a list is expected) would be silently replaced by an empty default and
    persisted, dropping caller data without a sound.

    This stricter variant:
      - ``None`` -> ``empty_default`` (the caller supplied nothing).
      - a value already of ``expected_type`` -> used as-is.
      - a ``str`` that JSON-decodes to ``expected_type`` -> the decoded value.
      - anything else (a non-None wrong-type that cannot be coerced) ->
        ``TypeError``. We refuse to silently persist an empty default in
        place of meaningful but mistyped data.
    """
    if val is None:
        return empty_default
    if isinstance(val, expected_type):
        return val
    if isinstance(val, str) and expected_type in (list, dict):
        try:
            parsed = json.loads(val)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, expected_type):
            return parsed
    raise TypeError(
        f"expected {expected_type.__name__} "
        f"(or JSON {expected_type.__name__} string); got {type(val).__name__}"
    )


def _dedup_ids(ids: Any) -> list[str]:
    """Normalise an id argument to a deduped, first-seen-order list of
    non-empty strings.

    Single source of truth for the batched-read tools (``get_stories``,
    ``get_memories``). Tolerates the three shapes an MCP caller can send: a
    native list, a bare id string, or a JSON-encoded list string. Non-string /
    empty members are dropped; genuine ids that simply do not resolve are
    surfaced in ``missing`` by the caller, never silently swallowed here.
    """
    raw = coerce_str_or_container(ids, list)
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


def coerce_str_or_container(val: Any, expected_type: type) -> Any:
    """Coerce a polymorphic ``Union[container, str, None]`` field.

    For params that legitimately accept either a native container or a bare
    string, ``coerce(val, dict)`` would null a real string — silent data loss.
    This decodes only a JSON string that *parses to the expected container*;
    a plain (non-JSON) string is preserved verbatim, a native container is
    kept, and None passes through. The string is never forced into a dict.
    """
    if val is None:
        return None
    if isinstance(val, expected_type):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
        except (ValueError, TypeError):
            return val
        return parsed if isinstance(parsed, expected_type) else val
    return val


# ---------------------------------------------------------------------------
# Kwarg normalisation — per-tool alias / ignore tables
# ---------------------------------------------------------------------------

def normalize_kwargs(func: Callable) -> Callable:
    """Remap caller kwarg synonyms to canonical params before invocation.

    Reads ``_ALIASES`` (synonym -> canonical) and ``_IGNORED`` (drop+warn)
    from the wrapped function's own module. Genuinely-unknown kwargs are
    left untouched so the wrapped signature still raises the standard
    ``unexpected keyword argument`` TypeError — typos are not swallowed.

    Raises TypeError if a synonym and its canonical (or two synonyms of the
    same canonical) are both supplied: an aliasing collision is ambiguous
    and must fail loud, not silently pick a winner.

    The tables are read from ``func.__globals__`` (not via module import) so
    this works both as a normal package import and inside the Othrys
    served-source sandbox, where each tool is exec'd into a synthetic
    namespace that is not importable by name.
    """
    g = func.__globals__
    aliases: dict[str, str] = g.get("_ALIASES", {})
    ignored: set[str] = g.get("_IGNORED", set())

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        for name in list(kwargs):
            if name in ignored:
                _log.warning(
                    "%s: ignoring unsupported argument '%s'",
                    func.__name__, name,
                )
                kwargs.pop(name)
        remapped: dict[str, Any] = {}
        for name in list(kwargs):
            canonical = aliases.get(name)
            if canonical is None:
                continue
            value = kwargs.pop(name)
            if canonical in kwargs or canonical in remapped:
                raise TypeError(
                    f"{func.__name__}() received conflicting arguments for "
                    f"'{canonical}': both it and alias '{name}' were supplied"
                )
            remapped[canonical] = value
        kwargs.update(remapped)
        return func(*args, **kwargs)

    return wrapper
