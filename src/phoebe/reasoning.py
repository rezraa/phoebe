# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Graph reasoning — traversals and analysis over Phoebe's tome.

These are the tools that make Phoebe more than CRUD. She walks edges,
traces causality, detects patterns, and surfaces insights.
"""

from __future__ import annotations

import json
from typing import Any


class Reasoner:
    """Graph reasoning engine over a Phoebe tome."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def _execute(self, query: str, params: dict[str, Any] | None = None) -> list:
        result = self._conn.execute(query, parameters=params or {})
        rows = []
        while result.has_next():
            rows.append(result.get_next())
        return rows

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

    def open_questions(self, project: str | None = None) -> list[dict]:
        """What's still unresolved?"""
        conditions = "m.status = 'open'"
        params: dict[str, Any] = {}
        if project:
            conditions += " AND m.project = $project"
            params["project"] = project
        rows = self._execute(
            f"MATCH (m:memories) WHERE {conditions} AND m.memory_type IN ['decision', 'question', 'assumption'] "
            "RETURN m ORDER BY m.timestamp DESC",
            params,
        )
        return [r[0] for r in rows]

    def failed_approaches(self, project: str | None = None) -> list[dict]:
        """What did we try that failed?"""
        conditions = "m.outcome = 'failure'"
        params: dict[str, Any] = {}
        if project:
            conditions += " AND m.project = $project"
            params["project"] = project
        rows = self._execute(
            f"MATCH (m:memories) WHERE {conditions} RETURN m ORDER BY m.timestamp DESC",
            params,
        )
        return [r[0] for r in rows]

    def unvalidated_assumptions(self, project: str | None = None) -> list[dict]:
        """What assumptions are we still making?"""
        conditions = "m.memory_type = 'assumption' AND m.status <> 'superseded'"
        params: dict[str, Any] = {}
        if project:
            conditions += " AND m.project = $project"
            params["project"] = project
        rows = self._execute(
            f"MATCH (m:memories) WHERE {conditions} RETURN m ORDER BY m.timestamp DESC",
            params,
        )
        return [r[0] for r in rows]

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
        Returns: recent decisions, open questions, failed approaches,
        unvalidated assumptions, and relevant memories.
        """
        brief: dict[str, Any] = {"project": project}

        # Recent decisions
        decisions = self.query_by_type(project, "decision", limit=limit)
        brief["recent_decisions"] = decisions

        # Open items
        brief["open_questions"] = self.open_questions(project)
        brief["unvalidated_assumptions"] = self.unvalidated_assumptions(project)
        brief["failed_approaches"] = self.failed_approaches(project)

        # Topic-specific memories
        if topic:
            rows = self._execute(
                "MATCH (m:memories)-[:about]->(e:entities) "
                "WHERE m.project = $project AND e.name CONTAINS $topic "
                "RETURN m ORDER BY m.timestamp DESC LIMIT $limit",
                {"project": project, "topic": topic, "limit": limit},
            )
            brief["topic_memories"] = [r[0] for r in rows]

        return brief

    def query_by_type(self, project: str, memory_type: str, limit: int = 20) -> list[dict]:
        """Get memories of a specific type for a project."""
        rows = self._execute(
            "MATCH (m:memories) WHERE m.project = $project AND m.memory_type = $type "
            "RETURN m ORDER BY m.timestamp DESC LIMIT $limit",
            {"project": project, "type": memory_type, "limit": limit},
        )
        return [r[0] for r in rows]
