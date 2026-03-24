# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Graph store — CRUD operations on Phoebe's Kuzu tome.

All writes go through this module. Queries return plain dicts.
"""

from __future__ import annotations

import json
from typing import Any


class GraphStore:
    """CRUD operations on a Phoebe tome (Kuzu connection)."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _execute(self, query: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Execute a Cypher query and return results as list of dicts."""
        result = self._conn.execute(query, parameters=params or {})
        rows = []
        while result.has_next():
            rows.append(result.get_next())
        return rows

    def _insert_node(self, table: str, data: dict[str, Any]) -> str:
        """Insert a node and return its id."""
        cols = ", ".join(data.keys())
        params = ", ".join(f"${k}" for k in data.keys())
        query = f"CREATE (n:{table} {{{cols}}}) SET " + ", ".join(
            f"n.{k} = ${k}" for k in data.keys()
        )
        # Kuzu CREATE syntax: CREATE (n:table {key: $key, ...})
        props = ", ".join(f"{k}: ${k}" for k in data.keys())
        query = f"CREATE (:{table} {{{props}}})"
        self._conn.execute(query, parameters=data)
        return data["id"]

    def _create_edge(
        self,
        rel_table: str,
        from_table: str,
        from_id: str,
        to_table: str,
        to_id: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Create a relationship between two nodes."""
        prop_str = ""
        params: dict[str, Any] = {"from_id": from_id, "to_id": to_id}
        if properties:
            prop_assignments = ", ".join(f"r.{k} = ${k}" for k in properties)
            prop_str = f" SET {prop_assignments}"
            params.update(properties)
        query = (
            f"MATCH (a:{from_table}), (b:{to_table}) "
            f"WHERE a.id = $from_id AND b.id = $to_id "
            f"CREATE (a)-[r:{rel_table}]->(b)"
            f"{prop_str}"
        )
        self._conn.execute(query, parameters=params)

    # ------------------------------------------------------------------
    # Memory CRUD
    # ------------------------------------------------------------------

    def add_memory(self, memory: dict[str, Any]) -> str:
        """Insert a memory node. Returns the memory id."""
        return self._insert_node("memories", memory)

    def get_memory(self, memory_id: str) -> dict[str, Any] | None:
        """Get a single memory by id."""
        rows = self._execute(
            "MATCH (m:memories) WHERE m.id = $id RETURN m",
            {"id": memory_id},
        )
        return rows[0][0] if rows else None

    def query_memories(
        self,
        *,
        project: str | None = None,
        memory_type: str | None = None,
        agent: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Query memories with optional filters."""
        conditions = []
        params: dict[str, Any] = {}
        if project:
            conditions.append("m.project = $project")
            params["project"] = project
        if memory_type:
            conditions.append("m.memory_type = $memory_type")
            params["memory_type"] = memory_type
        if agent:
            conditions.append("m.agent = $agent")
            params["agent"] = agent
        if status:
            conditions.append("m.status = $status")
            params["status"] = status

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"MATCH (m:memories){where} RETURN m ORDER BY m.timestamp DESC LIMIT {limit}"
        rows = self._execute(query, params)
        return [r[0] for r in rows]

    def update_memory_status(self, memory_id: str, status: str) -> None:
        """Update a memory's status."""
        self._conn.execute(
            "MATCH (m:memories) WHERE m.id = $id SET m.status = $status",
            parameters={"id": memory_id, "status": status},
        )

    def supersede_memory(self, old_id: str, new_memory: dict[str, Any], reason: str) -> str:
        """Create a new memory that supersedes an old one."""
        new_id = self.add_memory(new_memory)
        self.update_memory_status(old_id, "superseded")
        self._create_edge("supersedes", "memories", new_id, "memories", old_id, {"reason": reason})
        return new_id

    # ------------------------------------------------------------------
    # Source CRUD
    # ------------------------------------------------------------------

    def add_source(self, source: dict[str, Any]) -> str:
        """Insert a source node. Returns the source id."""
        return self._insert_node("sources", source)

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        """Get a single source by id."""
        rows = self._execute(
            "MATCH (s:sources) WHERE s.id = $id RETURN s",
            {"id": source_id},
        )
        return rows[0][0] if rows else None

    def find_source_by_uri(self, uri: str) -> dict[str, Any] | None:
        """Find a source by its URI (deduplicate before inserting)."""
        rows = self._execute(
            "MATCH (s:sources) WHERE s.uri = $uri RETURN s",
            {"uri": uri},
        )
        return rows[0][0] if rows else None

    def get_or_create_source(self, source: dict[str, Any]) -> str:
        """Find existing source by URI or create new. Returns source id."""
        existing = self.find_source_by_uri(source["uri"])
        if existing:
            return existing["id"]
        return self.add_source(source)

    def mark_source_stale(self, source_id: str) -> None:
        """Mark a source as stale (no longer reachable)."""
        self._conn.execute(
            "MATCH (s:sources) WHERE s.id = $id SET s.stale = true",
            parameters={"id": source_id},
        )

    def mark_source_verified(self, source_id: str, model: str = "") -> None:
        """Mark a source as freshly verified."""
        from phoebe.models import _now
        params: dict[str, Any] = {"id": source_id, "ts": _now()}
        set_clause = "SET s.last_verified = $ts, s.stale = false"
        if model:
            set_clause += ", s.extraction_model = $model"
            params["model"] = model
        self._conn.execute(
            f"MATCH (s:sources) WHERE s.id = $id {set_clause}",
            parameters=params,
        )

    def get_stale_sources(self) -> list[dict]:
        """Return all stale sources."""
        rows = self._execute("MATCH (s:sources) WHERE s.stale = true RETURN s")
        return [r[0] for r in rows]

    def query_sources(self, source_type: str | None = None, limit: int = 50) -> list[dict]:
        """Query sources with optional type filter."""
        if source_type:
            rows = self._execute(
                f"MATCH (s:sources) WHERE s.source_type = $type RETURN s LIMIT {limit}",
                {"type": source_type},
            )
        else:
            rows = self._execute(f"MATCH (s:sources) RETURN s LIMIT {limit}")
        return [r[0] for r in rows]

    # ------------------------------------------------------------------
    # Entity CRUD
    # ------------------------------------------------------------------

    def add_entity(self, entity: dict[str, Any]) -> str:
        """Insert an entity node. Returns the entity id."""
        return self._insert_node("entities", entity)

    def find_entity_by_name(self, name: str) -> dict[str, Any] | None:
        """Find an entity by name."""
        rows = self._execute(
            "MATCH (e:entities) WHERE e.name = $name RETURN e",
            {"name": name},
        )
        return rows[0][0] if rows else None

    def get_or_create_entity(self, entity: dict[str, Any]) -> str:
        """Find existing entity by name or create new. Returns entity id."""
        existing = self.find_entity_by_name(entity["name"])
        if existing:
            return existing["id"]
        return self.add_entity(entity)

    # ------------------------------------------------------------------
    # Milestone CRUD
    # ------------------------------------------------------------------

    def add_milestone(self, milestone: dict[str, Any]) -> str:
        """Insert a milestone node. Returns the milestone id."""
        return self._insert_node("milestones", milestone)

    def find_milestone_by_name(self, name: str) -> dict[str, Any] | None:
        """Find a milestone by name."""
        rows = self._execute(
            "MATCH (ms:milestones) WHERE ms.name = $name RETURN ms",
            {"name": name},
        )
        return rows[0][0] if rows else None

    def get_or_create_milestone(self, milestone: dict[str, Any]) -> str:
        """Find existing milestone by name or create new. Returns milestone id."""
        existing = self.find_milestone_by_name(milestone["name"])
        if existing:
            return existing["id"]
        return self.add_milestone(milestone)

    # ------------------------------------------------------------------
    # Edge creation (typed helpers)
    # ------------------------------------------------------------------

    def link_memory_to_source(self, memory_id: str, source_id: str) -> None:
        """extracted_from: memory was extracted from source."""
        self._create_edge("extracted_from", "memories", memory_id, "sources", source_id)

    def link_memory_to_entity(self, memory_id: str, entity_id: str, rel: str = "about") -> None:
        """Link memory to entity. rel: 'about', 'decided_by', 'affects'."""
        self._create_edge(rel, "memories", memory_id, "entities", entity_id)

    def link_memory_to_milestone(self, memory_id: str, milestone_id: str) -> None:
        """occurred_during: memory happened during milestone."""
        self._create_edge("occurred_during", "memories", memory_id, "milestones", milestone_id)

    def link_memory_caused_by(self, memory_id: str, cause_id: str, reason: str = "") -> None:
        """caused_by: this memory was caused by another."""
        self._create_edge("caused_by", "memories", memory_id, "memories", cause_id, {"reason": reason})

    def link_memories_contradict(self, id_a: str, id_b: str, resolution: str = "") -> None:
        """contradicts: two memories are in conflict."""
        self._create_edge("contradicts", "memories", id_a, "memories", id_b, {"resolution": resolution})

    def link_memories_corroborate(self, id_a: str, id_b: str) -> None:
        """corroborates: two memories agree."""
        self._create_edge("corroborates", "memories", id_a, "memories", id_b)

    def link_memory_blocked_by(self, blocked_id: str, blocker_id: str, reason: str = "") -> None:
        """blocked_by: this memory is blocked by another."""
        self._create_edge("blocked_by", "memories", blocked_id, "memories", blocker_id, {"reason": reason})

    def link_entity_depends_on(self, entity_id: str, dependency_id: str, dep_type: str = "") -> None:
        """depends_on: entity depends on another entity."""
        self._create_edge("depends_on", "entities", entity_id, "entities", dependency_id, {"dependency_type": dep_type})

    def link_entity_owns(self, owner_id: str, owned_id: str, role: str = "owner") -> None:
        """owns: entity (person/team) owns another entity (system/service)."""
        self._create_edge("owns", "entities", owner_id, "entities", owned_id, {"role": role})

    def link_entity_introduced_in(self, entity_id: str, milestone_id: str) -> None:
        """introduced_in: entity was introduced in this milestone."""
        self._create_edge("introduced_in", "entities", entity_id, "milestones", milestone_id)

    def link_entity_deprecated_in(self, entity_id: str, milestone_id: str) -> None:
        """deprecated_in: entity was deprecated in this milestone."""
        self._create_edge("deprecated_in", "entities", entity_id, "milestones", milestone_id)

    def link_source_contains(self, parent_id: str, child_id: str) -> None:
        """contains: source contains another source (hierarchy)."""
        self._create_edge("contains", "sources", parent_id, "sources", child_id)

    # ------------------------------------------------------------------
    # Plan CRUD
    # ------------------------------------------------------------------

    def add_plan(self, plan: dict[str, Any]) -> str:
        """Insert a plan node. Returns the plan id."""
        return self._insert_node("plans", plan)

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        """Get a single plan by id."""
        rows = self._execute(
            "MATCH (p:plans) WHERE p.id = $id RETURN p",
            {"id": plan_id},
        )
        return rows[0][0] if rows else None

    def get_latest_plan(self) -> dict[str, Any] | None:
        """Get the most recently created plan."""
        rows = self._execute(
            "MATCH (p:plans) RETURN p ORDER BY p.created_at DESC LIMIT 1"
        )
        return rows[0][0] if rows else None

    def update_plan(self, plan_id: str, **fields: Any) -> None:
        """Update plan fields."""
        from phoebe.models import _now
        fields["updated_at"] = _now()
        assignments = ", ".join(f"p.{k} = ${k}" for k in fields)
        self._conn.execute(
            f"MATCH (p:plans) WHERE p.id = $id SET {assignments}",
            parameters={"id": plan_id, **fields},
        )

    # ------------------------------------------------------------------
    # Epic CRUD
    # ------------------------------------------------------------------

    def add_epic(self, epic: dict[str, Any]) -> str:
        """Insert an epic node. Returns the epic id."""
        return self._insert_node("epics", epic)

    def get_epics_for_plan(self, plan_id: str) -> list[dict]:
        """Get all epics for a plan, ordered by sequence."""
        rows = self._execute(
            "MATCH (e:epics) WHERE e.plan_id = $plan_id "
            "RETURN e ORDER BY e.sequence",
            {"plan_id": plan_id},
        )
        return [r[0] for r in rows]

    def update_epic(self, epic_id: str, **fields: Any) -> None:
        """Update epic fields."""
        assignments = ", ".join(f"e.{k} = ${k}" for k in fields)
        self._conn.execute(
            f"MATCH (e:epics) WHERE e.id = $id SET {assignments}",
            parameters={"id": epic_id, **fields},
        )

    # ------------------------------------------------------------------
    # Story CRUD
    # ------------------------------------------------------------------

    def add_story(self, story: dict[str, Any]) -> str:
        """Insert a story node. Returns the story id."""
        return self._insert_node("stories", story)

    def get_stories_for_epic(self, epic_id: str) -> list[dict]:
        """Get all stories for an epic, ordered by sequence."""
        rows = self._execute(
            "MATCH (s:stories) WHERE s.epic_id = $epic_id "
            "RETURN s ORDER BY s.sequence",
            {"epic_id": epic_id},
        )
        return [r[0] for r in rows]

    def update_story(self, story_id: str, **fields: Any) -> None:
        """Update story fields."""
        from phoebe.models import _now
        fields["updated_at"] = _now()
        assignments = ", ".join(f"s.{k} = ${k}" for k in fields)
        self._conn.execute(
            f"MATCH (s:stories) WHERE s.id = $id SET {assignments}",
            parameters={"id": story_id, **fields},
        )

    def get_story(self, story_id: str) -> dict[str, Any] | None:
        """Get a single story by id."""
        rows = self._execute(
            "MATCH (s:stories) WHERE s.id = $id RETURN s",
            {"id": story_id},
        )
        return rows[0][0] if rows else None

    # ------------------------------------------------------------------
    # Plan edge creation
    # ------------------------------------------------------------------

    def link_plan_to_epic(self, plan_id: str, epic_id: str, sequence: int) -> None:
        """has_epic: plan contains epic."""
        self._create_edge("has_epic", "plans", plan_id, "epics", epic_id, {"sequence": sequence})

    def link_epic_to_story(self, epic_id: str, story_id: str, sequence: int) -> None:
        """has_story: epic contains story."""
        self._create_edge("has_story", "epics", epic_id, "stories", story_id, {"sequence": sequence})

    def link_story_to_agent(self, story_id: str, agent_id: str) -> None:
        """assigned_to: story is assigned to a Titan."""
        self._create_edge("assigned_to", "stories", story_id, "agents", agent_id)

    def link_story_depends_on(self, story_id: str, dependency_id: str, reason: str = "") -> None:
        """story_depends_on: story depends on another story."""
        self._create_edge("story_depends_on", "stories", story_id, "stories", dependency_id, {"reason": reason})

    def link_story_produces(self, story_id: str, memory_id: str) -> None:
        """produces: story produced this memory as an artifact."""
        self._create_edge("produces", "stories", story_id, "memories", memory_id)

    def link_plan_to_milestone(self, plan_id: str, milestone_id: str) -> None:
        """plan_milestone: plan targets a milestone."""
        self._create_edge("plan_milestone", "plans", plan_id, "milestones", milestone_id)
