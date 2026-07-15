# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Graph reasoning — traversals and analysis over Phoebe's tome.

These are the tools that make Phoebe more than CRUD. She walks edges,
traces causality, detects patterns, and surfaces insights.

Includes code_context section in brief() for file-referencing topics and
structural delta detection after sync (persisted as code_change memories).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from phoebe.store import (
    GraphStore,
    _MEMORY_STORED_COLS,
    _PLAN_SKELETON_COLS,
    memory_index_record,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# File-reference detection for code_context in brief()
# ---------------------------------------------------------------------------

# Matches file-like references: foo/bar.py, src/module.ts, etc.
_FILE_REF_RE = re.compile(
    r'(?:^|[\s,;(])('
    r'(?:[\w./-]+/)?'        # optional directory path
    r'[\w.-]+'               # filename stem
    r'\.(?:py|ts|tsx|js|jsx|rs|swift|kt|go|java|rb|c|cpp|h|hpp)'  # extension
    r')(?:[\s,;):]|$)',
)

# Matches dotted module names like othrys.code_topology._query
_MODULE_REF_RE = re.compile(
    r'(?:^|[\s,;(])'
    r'((?:[a-zA-Z_]\w*\.){2,}[a-zA-Z_]\w*)'  # at least 3 dotted parts
    r'(?:[\s,;):]|$)',
)


def _detect_file_references(topic: str) -> list[str]:
    """Extract file paths and module references from a topic string.

    Returns a list of file-path-like strings found in the topic.
    Module references (dotted names) are converted to path form.
    """
    refs: list[str] = []

    # Direct file paths
    for m in _FILE_REF_RE.finditer(topic):
        refs.append(m.group(1))

    # Dotted module names -> path form
    for m in _MODULE_REF_RE.finditer(topic):
        mod = m.group(1)
        # Convert dots to slashes and add .py extension
        path = mod.replace(".", "/") + ".py"
        refs.append(path)

    return refs


def _code_context_section(topic: str, conn: Any) -> str:
    """Build a code_context section for brief() when topic references files.

    Calls code_context() for dependencies and changes on the first
    detected file reference.  Returns a formatted string under 2KB,
    or empty string if no file reference found or code_topology unavailable.
    """
    refs = _detect_file_references(topic)
    if not refs:
        return ""

    try:
        from othrys.code_topology._query import code_context
    except ImportError:
        # Not running in Othrys mode -- code_topology not available
        return ""

    file_ref = refs[0]
    sections: list[str] = []

    try:
        # Dependencies -- what does this file import/call?
        deps = code_context(
            file_ref, "dependencies", ".", conn,
        )
        if deps.get("symbols"):
            sym_names = [s["name"] for s in deps["symbols"][:15]]
            sections.append(f"Symbols: {', '.join(sym_names)}")
        if deps.get("calls"):
            call_strs = [
                f"{c['from_symbol']}->{c['to_symbol']}({c.get('to_file', '?')})"
                for c in deps["calls"][:10]
            ]
            sections.append(f"Calls: {', '.join(call_strs)}")
        if deps.get("imports"):
            imp_strs = [
                f"{i['to_symbol']}({i.get('to_file', i.get('source_module', '?'))})"
                for i in deps["imports"][:10]
            ]
            sections.append(f"Imports: {', '.join(imp_strs)}")

        # Changes -- what symbols changed since last sync?
        changes = code_context(
            file_ref, "changes", ".", conn,
        )
        if changes.get("changed_files"):
            for cf in changes["changed_files"][:5]:
                status = cf.get("status", "unknown")
                old_syms = [s["name"] for s in cf.get("symbols_before", [])[:10]]
                sections.append(
                    f"Changed ({status}): {cf['file']} "
                    f"[was: {', '.join(old_syms) or 'none'}]"
                )
    except Exception as exc:
        log.debug("_code_context_section failed for %r: %s", file_ref, exc)
        return ""

    if not sections:
        return ""

    # Truncate to under 2KB
    result = f"Code context for {file_ref}:\n" + "\n".join(sections)
    if len(result) > 2000:
        result = result[:1997] + "..."
    return result


# ---------------------------------------------------------------------------
# Structural delta detection
# ---------------------------------------------------------------------------

def _detect_structural_delta(
    old_symbols: list[dict],
    new_symbols: list[dict],
) -> list[dict]:
    """Compare old and new symbol lists; return meaningful structural changes.

    Each returned dict has keys: action (added/deleted/changed), name, kind,
    and optionally old_signature/new_signature.

    Trivial changes (whitespace/comment-only, same signature and kind) are
    excluded.
    """
    old_by_name: dict[str, dict] = {}
    for s in old_symbols:
        key = s.get("name", "")
        if key:
            old_by_name[key] = s

    new_by_name: dict[str, dict] = {}
    for s in new_symbols:
        key = s.get("name", "")
        if key:
            new_by_name[key] = s

    old_names = set(old_by_name.keys())
    new_names = set(new_by_name.keys())

    deltas: list[dict] = []

    # Deleted symbols
    for name in sorted(old_names - new_names):
        deltas.append({
            "action": "deleted",
            "name": name,
            "kind": old_by_name[name].get("kind", "unknown"),
        })

    # Added symbols
    for name in sorted(new_names - old_names):
        deltas.append({
            "action": "added",
            "name": name,
            "kind": new_by_name[name].get("kind", "unknown"),
        })

    # Changed symbols (same name, different signature or kind)
    for name in sorted(old_names & new_names):
        old_s = old_by_name[name]
        new_s = new_by_name[name]

        # Compare kind and signature -- ignore line numbers (trivial)
        old_kind = old_s.get("kind", "")
        new_kind = new_s.get("kind", "")

        old_sig = (old_s.get("signature") or "").strip()
        new_sig = (new_s.get("signature") or "").strip()

        old_doc = (old_s.get("doc_string") or "").strip()
        new_doc = (new_s.get("doc_string") or "").strip()

        # Skip if only doc_string changed (comment-only change)
        if old_kind == new_kind and old_sig == new_sig:
            continue

        deltas.append({
            "action": "changed",
            "name": name,
            "kind": new_kind,
            "old_signature": old_sig,
            "new_signature": new_sig,
        })

    return deltas


def persist_structural_delta(
    deltas: list[dict],
    file_path: str,
    project: str,
    store: Any,
) -> list[str]:
    """Persist structural deltas as code_change memories in the tome.

    Args:
        deltas: Output from _detect_structural_delta().
        file_path: Relative file path that changed.
        project: Project name for the memories.
        store: A GraphStore instance for writing.

    Returns:
        List of memory IDs created.
    """
    if not deltas:
        return []

    from phoebe.models import make_memory

    memory_ids: list[str] = []
    for delta in deltas:
        action = delta["action"]
        name = delta["name"]
        kind = delta.get("kind", "symbol")

        if action == "added":
            content_str = f"New {kind} '{name}' added to {file_path}"
        elif action == "deleted":
            content_str = f"{kind.title()} '{name}' deleted from {file_path}"
        else:
            old_sig = delta.get("old_signature", "")
            new_sig = delta.get("new_signature", "")
            content_str = (
                f"{kind.title()} '{name}' changed in {file_path}: "
                f"'{old_sig}' -> '{new_sig}'"
            )

        mem = make_memory(
            content={"description": content_str, "delta": delta, "file": file_path},
            memory_type="code_change",
            project=project,
            agent="code_sync",
        )
        memory_id = store.add_memory(mem)
        memory_ids.append(memory_id)

    return memory_ids


# ---------------------------------------------------------------------------
# Memory-facet WHERE cores + shared ORDER/LIMIT tail.
# ---------------------------------------------------------------------------
# Single source of truth for each facet's filter: context_brief derives BOTH
# the limit-capped id list AND the true unbounded COUNT(*) from the same
# ``(match, params)`` spec, so the count can never silently drift from the list.
_FACET_ORDER = " ORDER BY m.timestamp DESC LIMIT $limit"
_OPEN_QUESTIONS_COND = (
    "m.status = 'open' "
    "AND m.memory_type IN ['decision', 'question', 'assumption']"
)
_FAILED_APPROACHES_COND = "m.outcome = 'failure'"
_UNVALIDATED_COND = "m.memory_type = 'assumption' AND m.status <> 'superseded'"


class Reasoner:
    """Graph reasoning engine over a Phoebe tome."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn
        # Reuse the store's single column-projection primitive (_project) for
        # memory/plan facet reads instead of re-rolling RETURN clauses here.
        self._store = GraphStore(conn)

    def _execute(self, query: str, params: dict[str, Any] | None = None) -> list:
        result = self._conn.execute(query, parameters=params or {})
        rows = []
        while result.has_next():
            rows.append(result.get_next())
        return rows

    def _facet_spec(
        self, base_condition: str, project: str | None, limit: int,
        *, extra_params: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Build the ``(match, params)`` for a ``memories`` facet: ``base_condition``
        plus an optional byte-exact project scope. The SINGLE source of a facet's
        WHERE — the capped id list and the true COUNT(*) both consume it, so they
        can never drift (see :meth:`_facet_total`). ``limit`` is always BOUND."""
        conditions = base_condition
        params: dict[str, Any] = {"limit": limit}
        if extra_params:
            params.update(extra_params)
        if project:
            conditions += " AND m.project = $project"
            params["project"] = project
        return f"MATCH (m:memories) WHERE {conditions}", params

    def _facet_total(self, match: str, params: dict[str, Any]) -> int:
        """UNBOUNDED ``COUNT(*)`` over a facet's WHERE — the true total behind the
        ``limit``-capped id list. ``context_brief``'s ``counts`` uses this so an
        agent sees 'showing N of M' and knows when to ``recall`` for the rest.
        ``$limit`` is dropped: the count query intentionally carries no LIMIT."""
        count_params = {k: v for k, v in params.items() if k != "limit"}
        rows = self._execute(f"{match} RETURN COUNT(*)", count_params)
        return int(rows[0][0]) if rows else 0

    # ------------------------------------------------------------------
    # Causal chain traversal
    # ------------------------------------------------------------------

    def trace_causes(self, memory_id: str, max_depth: int = 5) -> list[dict]:
        """Walk caused_by edges backwards to find the root cause chain.

        Returns a list of memories from most recent to root cause.
        """
        rows = self._execute(
            f"MATCH (m:memories)-[:caused_by*1..{max_depth}]->(cause:memories) "
            "WHERE m.id = $id "
            "RETURN cause ORDER BY cause.timestamp DESC",
            {"id": memory_id},
        )
        return [r[0] for r in rows]

    def trace_effects(self, memory_id: str, max_depth: int = 5) -> list[dict]:
        """Walk caused_by edges forward to find downstream effects."""
        rows = self._execute(
            f"MATCH (effect:memories)-[:caused_by*1..{max_depth}]->(m:memories) "
            "WHERE m.id = $id "
            "RETURN effect ORDER BY effect.timestamp ASC",
            {"id": memory_id},
        )
        return [r[0] for r in rows]

    # ------------------------------------------------------------------
    # Decision currency check
    # ------------------------------------------------------------------

    def is_current(self, memory_id: str) -> dict[str, Any]:
        """Check if a decision is still current or has been superseded."""
        rows = self._execute(
            "MATCH (newer:memories)-[s:supersedes]->(m:memories) "
            "WHERE m.id = $id "
            "RETURN newer, s.reason",
            {"id": memory_id},
        )
        if rows:
            return {
                "current": False,
                "superseded_by": rows[0][0],
                "reason": rows[0][1],
            }
        return {"current": True}

    # ------------------------------------------------------------------
    # Entity impact analysis
    # ------------------------------------------------------------------

    def blast_radius(self, entity_name: str) -> dict[str, Any]:
        """What depends on this entity? What's the blast radius of changing it?"""
        rows = self._execute(
            "MATCH (dep:entities)-[d:depends_on]->(e:entities) "
            "WHERE e.name = $name "
            "RETURN dep, d.dependency_type",
            {"name": entity_name},
        )
        dependents = [{"entity": r[0], "dependency_type": r[1]} for r in rows]

        # Also find memories that affect this entity
        affected = self._execute(
            "MATCH (m:memories)-[:affects]->(e:entities) "
            "WHERE e.name = $name "
            "RETURN m ORDER BY m.timestamp DESC LIMIT 10",
            {"name": entity_name},
        )
        return {
            "entity": entity_name,
            "dependents": dependents,
            "dependent_count": len(dependents),
            "recent_changes": [r[0] for r in affected],
        }

    # ------------------------------------------------------------------
    # Expertise detection
    # ------------------------------------------------------------------

    def who_knows(self, topic: str, limit: int = 5) -> list[dict]:
        """Who knows the most about a topic? Count memories per person."""
        rows = self._execute(
            "MATCH (m:memories)-[:about]->(e:entities) "
            "WHERE e.name = $topic "
            "MATCH (m)-[:decided_by]->(person:entities) "
            "WHERE person.entity_type = 'person' "
            "RETURN person.name, COUNT(m) AS expertise "
            "ORDER BY expertise DESC LIMIT $limit",
            {"topic": topic, "limit": limit},
        )
        return [{"person": r[0], "memory_count": r[1]} for r in rows]

    # ------------------------------------------------------------------
    # Ownership lookup
    # ------------------------------------------------------------------

    def who_owns(self, entity_name: str) -> list[dict]:
        """Who owns/maintains this entity?"""
        rows = self._execute(
            "MATCH (owner:entities)-[o:owns]->(e:entities) "
            "WHERE e.name = $name "
            "RETURN owner, o.role",
            {"name": entity_name},
        )
        return [{"owner": r[0], "role": r[1]} for r in rows]

    # ------------------------------------------------------------------
    # Timeline queries
    # ------------------------------------------------------------------

    def what_happened_during(self, milestone_name: str) -> list[dict]:
        """What memories are anchored to this milestone?"""
        rows = self._execute(
            "MATCH (m:memories)-[:occurred_during]->(ms:milestones) "
            "WHERE ms.name = $name "
            "RETURN m ORDER BY m.timestamp",
            {"name": milestone_name},
        )
        return [r[0] for r in rows]

    def entity_timeline(self, entity_name: str) -> list[dict]:
        """How has an entity evolved over time?"""
        rows = self._execute(
            "MATCH (m:memories)-[:about]->(e:entities) "
            "WHERE e.name = $name "
            "RETURN m ORDER BY m.timestamp",
            {"name": entity_name},
        )
        return [r[0] for r in rows]

    # ------------------------------------------------------------------
    # Pattern detection
    # ------------------------------------------------------------------

    def recurring_issues(self, entity_name: str | None = None) -> list[dict]:
        """Find recurring incidents/issues for an entity or across the tome."""
        if entity_name:
            rows = self._execute(
                "MATCH (m:memories)-[:about]->(e:entities) "
                "WHERE e.name = $name AND m.memory_type = 'incident' "
                "RETURN e.name, COUNT(m) AS occurrences, COLLECT(m.timestamp) AS dates",
                {"name": entity_name},
            )
        else:
            rows = self._execute(
                "MATCH (m:memories)-[:about]->(e:entities) "
                "WHERE m.memory_type = 'incident' "
                "RETURN e.name, COUNT(m) AS occurrences, COLLECT(m.timestamp) AS dates "
                "ORDER BY occurrences DESC LIMIT 10",
            )
        return [
            {"entity": r[0], "occurrences": r[1], "dates": r[2]}
            for r in rows
        ]

    def open_questions(self, project: str | None = None, limit: int = 20) -> list[dict]:
        """What's still unresolved? BOUNDED by ``limit`` (D6: was unbounded).

        Projected stored columns (no ``RETURN m`` -> no _ID/_LABEL); ``limit``
        is BOUND, never f-string-interpolated.
        """
        match, params = self._facet_spec(_OPEN_QUESTIONS_COND, project, limit)
        return self._store._project(
            match=match, alias="m", cols=_MEMORY_STORED_COLS,
            params=params, order=_FACET_ORDER,
        )

    def failed_approaches(self, project: str | None = None, limit: int = 20) -> list[dict]:
        """What did we try that failed? BOUNDED by ``limit`` (D6: was unbounded)."""
        match, params = self._facet_spec(_FAILED_APPROACHES_COND, project, limit)
        return self._store._project(
            match=match, alias="m", cols=_MEMORY_STORED_COLS,
            params=params, order=_FACET_ORDER,
        )

    def unvalidated_assumptions(self, project: str | None = None, limit: int = 20) -> list[dict]:
        """What assumptions are we still making? BOUNDED by ``limit`` (D6)."""
        match, params = self._facet_spec(_UNVALIDATED_COND, project, limit)
        return self._store._project(
            match=match, alias="m", cols=_MEMORY_STORED_COLS,
            params=params, order=_FACET_ORDER,
        )

    # ------------------------------------------------------------------
    # Staleness analysis
    # ------------------------------------------------------------------

    def stale_source_impact(self) -> list[dict]:
        """What sources are stale and how many memories depend on them?"""
        rows = self._execute(
            "MATCH (m:memories)-[:extracted_from]->(s:sources) "
            "WHERE s.stale = true "
            "RETURN s.uri, s.source_type, COUNT(m) AS memories_at_risk "
            "ORDER BY memories_at_risk DESC",
        )
        return [
            {"uri": r[0], "source_type": r[1], "memories_at_risk": r[2]}
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Context brief generation
    # ------------------------------------------------------------------

    def context_brief(self, project: str, topic: str | None = None, limit: int = 20) -> dict[str, Any]:
        """Generate a context brief for a project (and optional topic).

        This is what Prometheus asks Phoebe for before summoning a Titan.

        Shape (body-store + ordered id-list facets — a memory is serialized
        ONCE, referenced by id everywhere):
          {
            "project": ...,
            "memories": { id: <lean index record>, ... },  # derived title, NO content
            "recent_decisions": [id, ...],        # ordered id lists
            "open_questions": [id, ...],
            "unvalidated_assumptions": [id, ...],
            "failed_approaches": [id, ...],
            "topic_memories": [id, ...],           # only when topic given
            "active_plans": [ <projected plan>, ... ],
            "counts": { facet: n, ... },           # TRUE unbounded total per facet
            "code_context": "...",                 # only when topic references a file
          }

        The brief is always rebuilt fresh (no cache) — it is cheap and
        freshness-critical. Each ``counts`` value is the UNBOUNDED total for
        that facet (a ``COUNT(*)`` over the same WHERE as the capped id list),
        so an agent can tell when to ``recall`` for rows beyond ``limit``.
        """
        brief: dict[str, Any] = {"project": project}
        memories: dict[str, dict] = {}
        counts: dict[str, int] = {}

        def _facet(name: str, match: str, params: dict[str, Any]) -> None:
            """Fold a facet's ``limit``-capped rows into the shared body-store,
            emit the ordered id list, AND record the TRUE unbounded total in
            ``counts`` (honest 'showing N of M' — see :meth:`_facet_total`)."""
            rows = self._store._project(
                match=match, alias="m", cols=_MEMORY_STORED_COLS,
                params=params, order=_FACET_ORDER,
            )
            ids: list[str] = []
            for raw in rows:
                mid = raw.get("id")
                if not mid:
                    continue
                if mid not in memories:
                    memories[mid] = memory_index_record(raw)
                ids.append(mid)
            brief[name] = ids
            counts[name] = self._facet_total(match, params)

        _facet("recent_decisions",
               *self._facet_spec("m.memory_type = 'decision'", project, limit))
        _facet("open_questions",
               *self._facet_spec(_OPEN_QUESTIONS_COND, project, limit))
        _facet("unvalidated_assumptions",
               *self._facet_spec(_UNVALIDATED_COND, project, limit))
        _facet("failed_approaches",
               *self._facet_spec(_FAILED_APPROACHES_COND, project, limit))

        # Active plans for this project — projected (no whole-node RETURN p).
        if project:
            try:
                brief["active_plans"] = self._store._project(
                    match="MATCH (p:plans) WHERE p.project = $project",
                    alias="p", cols=_PLAN_SKELETON_COLS,
                    params={"project": project, "limit": limit},
                    order=" ORDER BY p.created_at DESC LIMIT $limit",
                )
            except Exception:
                # plans table may not exist in standalone tome mode
                brief["active_plans"] = []
        else:
            brief["active_plans"] = []

        # Topic-specific memories (entity-name match).
        if topic:
            _facet(
                "topic_memories",
                "MATCH (m:memories)-[:about]->(e:entities) "
                "WHERE m.project = $project AND e.name CONTAINS $topic",
                {"project": project, "topic": topic, "limit": limit},
            )

        brief["memories"] = memories
        brief["counts"] = counts

        # code_context section for file-referencing topics
        if topic:
            code_section = _code_context_section(topic, self._conn)
            if code_section:
                brief["code_context"] = code_section

        return brief

    def query_by_type(self, project: str, memory_type: str, limit: int = 20) -> list[dict]:
        """Get memories of a specific type for a project (projected columns)."""
        match, params = self._facet_spec(
            "m.memory_type = $type", project, limit,
            extra_params={"type": memory_type},
        )
        return self._store._project(
            match=match, alias="m", cols=_MEMORY_STORED_COLS,
            params=params, order=_FACET_ORDER,
        )
