# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Phoebe MCP Server — Multimodal Knowledge Engine.

Thin wrappers that delegate to tool modules in phoebe/tools/.
Same pattern as Mnemos: server registers tools, modules do the work.
"""

from __future__ import annotations

import json as _json
from typing import Any, Union

from fastmcp import FastMCP

from phoebe.tools.remember import remember as _remember
from phoebe.tools.recall import recall as _recall
from phoebe.tools.trace import trace as _trace
from phoebe.tools.brief import brief as _brief
from phoebe.tools.blast_radius import blast_radius as _blast_radius
from phoebe.tools.who_knows import who_knows as _who_knows
from phoebe.tools.stats import stats as _stats
from phoebe.tools._shared import coerce


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
# Tool registrations — thin wrappers
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
        content: What was learned.
        memory_type: One of: decision, context, observation, requirement, risk,
                     lesson, incident, change, assumption, question.
        source_uri: Where this was learned (URL, file path, slack link, etc.).
        source_type: Type of source.
        project: Project name this memory belongs to.
        entities: List of entity names this memory is about.
        milestone: Milestone name this memory occurred during.
        confidence: 0.0-1.0 confidence score.
        status: Memory status: open, resolved, deferred, abandoned.
        outcome: For decisions/lessons: success, failure, abandoned, unknown.
        caused_by_id: ID of a memory that caused this one.

    Returns: {stored: true, memory_id, source_id, entities}
    """
    return _remember(
        content=content,
        memory_type=memory_type,
        source_uri=source_uri,
        source_type=source_type,
        project=project,
        entities=coerce(entities, list),
        milestone=milestone,
        confidence=confidence,
        status=status,
        outcome=outcome,
        caused_by_id=caused_by_id,
    )


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
        memory_type: Optional filter by type.
        entity: Optional filter by specific entity name.
        status: Optional filter by status.
        limit: Max results to return.

    Returns: {memories: [...], count: N}
    """
    return _recall(
        query=query,
        project=project,
        memory_type=memory_type,
        entity=entity,
        status=status,
        limit=limit,
    )


@mcp.tool()
def trace(
    memory_id: str,
    direction: str = "causes",
    max_depth: int = 5,
) -> dict:
    """Walk causal chains — why did this happen? What did it cause?

    Args:
        memory_id: The memory to trace from.
        direction: "causes" (backwards to root cause) or "effects" (forward).
        max_depth: Maximum chain depth.

    Returns: {memory_id, direction, chain, depth, current, superseded_by}
    """
    return _trace(memory_id=memory_id, direction=direction, max_depth=max_depth)


@mcp.tool()
def brief(
    project: str | None = None,
    topic: str | None = None,
    limit: int = 20,
) -> dict:
    """Generate a context brief for a project and optional topic.

    Args:
        project: Project name.
        topic: Optional topic to focus on.
        limit: Max results per category.

    Returns: {project, recent_decisions, open_questions, failed_approaches,
              unvalidated_assumptions, topic_memories}
    """
    return _brief(project=project, topic=topic, limit=limit)


@mcp.tool()
def blast_radius(entity_name: str) -> dict:
    """What depends on this entity? What's the impact of changing it?

    Args:
        entity_name: Name of the system/service/component to analyze.

    Returns: {entity, dependents, dependent_count, recent_changes}
    """
    return _blast_radius(entity_name=entity_name)


@mcp.tool()
def who_knows(topic: str, limit: int = 5) -> dict:
    """Who has the most expertise on a topic?

    Args:
        topic: Entity name to check expertise for.
        limit: Max results.

    Returns: {topic, experts: [{person, memory_count}]}
    """
    return _who_knows(topic=topic, limit=limit)


@mcp.tool()
def stats() -> dict:
    """Return tome statistics — node counts and stale source report.

    Returns: {memories, sources, entities, milestones, stale_sources}
    """
    return _stats()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    mcp.run()


if __name__ == "__main__":
    main()
