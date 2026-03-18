# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Phoebe MCP Server — Multimodal Knowledge Engine.

Stores memories of where she saw things and what they meant.
Answers WHY, not just WHAT.

Tools:
    remember       — store a memory with source reference and entity links
    recall         — query memories by project, type, topic, or entity
    trace          — walk causal chains (why did this happen? what did it cause?)
    brief          — generate a context brief for a project/topic
    ingest_source  — register a source and extract memories from it
    refresh        — re-verify sources and flag stale ones
    stats          — tome statistics
"""

from __future__ import annotations

import json as _json
from typing import Any, Union

from fastmcp import FastMCP

from phoebe.tome import Tome
from phoebe.store import GraphStore
from phoebe.reasoning import Reasoner
from phoebe.models import make_memory, make_source, make_entity, make_milestone


# ---------------------------------------------------------------------------
# Singleton tome — opened on first tool call
# ---------------------------------------------------------------------------

_tome: Tome | None = None
_store: GraphStore | None = None
_reasoner: Reasoner | None = None


def _get_store() -> GraphStore:
    global _tome, _store
    if _store is None:
        _tome = Tome()
        _tome.open()
        _store = GraphStore(_tome.connection())
    return _store


def _get_reasoner() -> Reasoner:
    global _tome, _reasoner
    if _reasoner is None:
        store = _get_store()  # ensures tome is open
        _reasoner = Reasoner(_tome.connection())
    return _reasoner


def _coerce(val: Any, expected_type: type) -> Any:
    """Coerce JSON-encoded strings to native types (MCP client compat)."""
    if val is None:
        return None
    if isinstance(val, str) and expected_type in (list, dict):
        try:
            parsed = _json.loads(val)
            if isinstance(parsed, expected_type):
                return parsed
        except (ValueError, TypeError):
            pass
    return val


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

mcp = FastMCP("phoebe", instructions=(
    "You are Phoebe, a knowledge engine. Your tome is your brain — a graph database of memories. "
    "When you recall something and it's there, answer from it with source citations. "
    "When your tome is empty on a topic, you LEARN — find authoritative sources, read them, "
    "and remember each fact (call remember with source_uri and entities). "
    "You never answer 'I don't know' without trying to learn first. "
    "Your tome grows with every interaction. What you learn now is available forever."
))


# ---------------------------------------------------------------------------
# Tool: remember
# ---------------------------------------------------------------------------

@mcp.tool()
def remember(
    content: str,
    memory_type: str,
    source_uri: str | None = None,
    source_type: str = "conversation",
    project: str | None = None,
    entities: Union[list[str], str, None] = None,
    milestone: str | None = None,
    confidence: float = 0.8,
    status: str = "open",
    outcome: str = "unknown",
    caused_by_id: str = "",
) -> dict:
    """Store a memory with source reference and entity links.

    Args:
        content: What was learned — structured description (will be JSON-encoded).
        memory_type: One of: decision, context, observation, requirement, risk,
                     lesson, incident, change, assumption, question.
        source_uri: Where this was learned (URL, file path, slack link, etc.).
        source_type: Type of source: slack, gdrive, confluence, file, url,
                     meeting, conversation, code, github_pr, github_issue, jira, email.
        project: Project name this memory belongs to.
        entities: List of entity names this memory is about.
        milestone: Milestone name this memory occurred during.
        confidence: 0.0-1.0 confidence score.
        status: Memory status: open, resolved, deferred, abandoned.
        outcome: For decisions/lessons: success, failure, abandoned, unknown.
        caused_by_id: ID of a memory that caused this one (causal chain).

    Returns: {stored: true, memory_id: "m-xxxx", source_id: "s-xxxx", entities: [...]}
    """
    store = _get_store()
    entities_list = _coerce(entities, list) or []

    # Create memory
    mem = make_memory(
        content={"description": content},
        memory_type=memory_type,
        project=project or "",
        confidence=confidence,
        status=status,
        outcome=outcome,
    )
    memory_id = store.add_memory(mem)

    # Link to source
    source_id = ""
    if source_uri:
        src = make_source(uri=source_uri, source_type=source_type)
        source_id = store.get_or_create_source(src)
        store.link_memory_to_source(memory_id, source_id)

    # Link to entities
    entity_ids = []
    for name in entities_list:
        ent = make_entity(name=name, entity_type="system")
        eid = store.get_or_create_entity(ent)
        store.link_memory_to_entity(memory_id, eid, "about")
        entity_ids.append(eid)

    # Link to milestone
    if milestone and milestone.strip():
        ms = make_milestone(name=milestone, milestone_type="sprint")
        ms_id = store.get_or_create_milestone(ms)
        store.link_memory_to_milestone(memory_id, ms_id)

    # Link causal chain
    if caused_by_id:
        store.link_memory_caused_by(memory_id, caused_by_id)

    return {
        "stored": True,
        "memory_id": memory_id,
        "source_id": source_id,
        "entities": entity_ids,
    }


# ---------------------------------------------------------------------------
# Tool: recall
# ---------------------------------------------------------------------------

@mcp.tool()
def recall(
    query: str,
    project: str | None = None,
    memory_type: str | None = None,
    entity: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> dict:
    """Query memories from the tome by topic, project, type, or entity.

    Args:
        query: Topic to search for in entity names and memory content.
        project: Optional filter by project name.
        memory_type: Optional filter by type: decision, risk, lesson, incident, etc.
        entity: Optional filter by specific entity name.
        status: Optional filter by status: open, resolved, deferred, abandoned.
        limit: Max results to return.

    Returns: {memories: [...], count: N}
    """
    store = _get_store()
    reasoner = _get_reasoner()

    if entity:
        # Entity-specific query
        conditions = ["e.name = $entity"]
        params: dict = {"entity": entity}
        if project:
            conditions.append("m.project = $project")
            params["project"] = project
        if memory_type:
            conditions.append("m.memory_type = $type")
            params["type"] = memory_type
        if status:
            conditions.append("m.status = $status")
            params["status"] = status
        where = " AND ".join(conditions)
        rows = reasoner._execute(
            f"MATCH (m:memories)-[:about]->(e:entities) WHERE {where} "
            f"RETURN m ORDER BY m.timestamp DESC LIMIT {limit}",
            params,
        )
        memories = [r[0] for r in rows]
    elif query:
        # BM25 full-text search on memory content + entity name fallback
        params: dict = {"query": query}
        project_filter = ""
        if project:
            project_filter = "AND m.project = $project "
            params["project"] = project

        seen = set()
        memories = []

        # Primary: BM25 search via FTS index
        try:
            fts_rows = reasoner._execute(
                f"CALL QUERY_FTS_INDEX('memories', 'memory_search', $query) "
                f"RETURN node, score ORDER BY score DESC LIMIT {limit}",
                {"query": query},
            )
            for r in fts_rows:
                node = r[0]
                mid = node.get("id", "")
                if project and node.get("project", "") != project:
                    continue
                if mid not in seen:
                    seen.add(mid)
                    memories.append(node)
        except Exception:
            pass  # FTS not available, fall through to entity search

        memories = memories[:limit]
    else:
        # Filtered query
        memories = store.query_memories(
            project=project or None,
            memory_type=memory_type or None,
            status=status or None,
            limit=limit,
        )

    return {"memories": memories, "count": len(memories)}


# ---------------------------------------------------------------------------
# Tool: trace
# ---------------------------------------------------------------------------

@mcp.tool()
def trace(
    memory_id: str,
    direction: str = "causes",
    max_depth: int = 5,
) -> dict:
    """Walk causal chains — why did this happen? What did it cause?

    Args:
        memory_id: The memory to trace from.
        direction: "causes" (walk backwards to root cause) or "effects" (walk forward).
        max_depth: Maximum chain depth to traverse.

    Returns: {chain: [...], depth: N, current: bool}
    """
    reasoner = _get_reasoner()

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


# ---------------------------------------------------------------------------
# Tool: brief
# ---------------------------------------------------------------------------

@mcp.tool()
def brief(
    project: str | None = None,
    topic: str | None = None,
    limit: int = 20,
) -> dict:
    """Generate a context brief for a project and optional topic.

    This is what Prometheus asks Phoebe for before summoning a Titan.
    Returns recent decisions, open questions, failed approaches,
    unvalidated assumptions, and topic-specific memories.

    Args:
        project: Project name.
        topic: Optional topic to focus on (entity name).
        limit: Max results per category.

    Returns: {project, recent_decisions, open_questions, failed_approaches,
              unvalidated_assumptions, topic_memories}
    """
    reasoner = _get_reasoner()
    return reasoner.context_brief(project or "", topic=topic or None, limit=limit)


# ---------------------------------------------------------------------------
# Tool: blast_radius
# ---------------------------------------------------------------------------

@mcp.tool()
def blast_radius(entity_name: str) -> dict:
    """What depends on this entity? What's the impact of changing it?

    Args:
        entity_name: Name of the system/service/component to analyze.

    Returns: {entity, dependents, dependent_count, recent_changes}
    """
    reasoner = _get_reasoner()
    return reasoner.blast_radius(entity_name)


# ---------------------------------------------------------------------------
# Tool: who_knows
# ---------------------------------------------------------------------------

@mcp.tool()
def who_knows(topic: str, limit: int = 5) -> dict:
    """Who has the most expertise on a topic?

    Args:
        topic: Entity name to check expertise for.
        limit: Max results.

    Returns: {topic, experts: [{person, memory_count}]}
    """
    reasoner = _get_reasoner()
    experts = reasoner.who_knows(topic, limit)
    return {"topic": topic, "experts": experts}


# ---------------------------------------------------------------------------
# Tool: stats
# ---------------------------------------------------------------------------

@mcp.tool()
def stats() -> dict:
    """Return tome statistics — node counts and stale source report.

    Returns: {memories, sources, entities, milestones, stale_sources}
    """
    global _tome
    store = _get_store()
    reasoner = _get_reasoner()

    counts = _tome.stats() if _tome else {}
    stale = reasoner.stale_source_impact()

    return {
        **counts,
        "stale_sources": stale,
        "stale_count": len(stale),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    mcp.run()


if __name__ == "__main__":
    main()
