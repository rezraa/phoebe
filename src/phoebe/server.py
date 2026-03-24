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
from phoebe.tools.create_plan import create_plan as _create_plan
from phoebe.tools.add_epic import add_epic as _add_epic
from phoebe.tools.add_story import add_story as _add_story
from phoebe.tools.update_story import update_story as _update_story
from phoebe.tools.get_plan import get_plan as _get_plan
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
# Execution pipeline tools — plans, epics, stories
# Prometheus designs. Phoebe writes. Titans execute.
# ---------------------------------------------------------------------------

@mcp.tool()
def create_plan(
    name: str,
    goal: str,
    epics: Union[list[dict], str] = "[]",
    conn: Any = None,
) -> dict:
    """Create a full execution plan with epics and stories.

    Prometheus designs the plan via council, then calls this to write it
    to Othrys. Creates plan, epic, and story nodes plus all relationships.

    Args:
        name: Plan name (e.g. "Build Theia Titan").
        goal: What the plan achieves.
        epics: List of epic dicts, each with name, description, sequence,
               acceptance_criteria, and a stories list. Each story has
               name, description, phase, assigned_titan, sequence,
               acceptance_criteria, and optional depends_on (list of
               story names).
        conn: Kuzu connection (injected by Othrys).

    Returns: {created, plan_id, epic_ids, story_ids, edge_counts}
    """
    return _create_plan(
        name=name,
        goal=goal,
        epics=coerce(epics, list),
        conn=conn,
    )


@mcp.tool()
def add_epic(
    plan_id: str,
    name: str,
    description: str,
    sequence: int,
    acceptance_criteria: str = "",
    stories: Union[list[dict], str, None] = None,
    conn: Any = None,
) -> dict:
    """Add an epic to an existing plan.

    Used when Prometheus adds scope mid-execution — new epics that
    weren't in the original plan.

    Args:
        plan_id: ID of the existing plan.
        name: Epic name.
        description: What this epic achieves.
        sequence: Order within the plan.
        acceptance_criteria: How we know it's done.
        stories: Optional list of story dicts (same format as create_plan).
        conn: Kuzu connection (injected by Othrys).

    Returns: {added, epic_id, story_ids}
    """
    return _add_epic(
        plan_id=plan_id,
        name=name,
        description=description,
        sequence=sequence,
        acceptance_criteria=acceptance_criteria,
        stories=coerce(stories, list),
        conn=conn,
    )


@mcp.tool()
def add_story(
    epic_id: str,
    name: str,
    description: str,
    phase: str,
    assigned_titan: str,
    sequence: int,
    acceptance_criteria: str = "",
    depends_on_ids: Union[list[str], str, None] = None,
    conn: Any = None,
) -> dict:
    """Add a story to an existing epic.

    Used for fix stories from adversarial review, or when Prometheus
    discovers new work mid-execution.

    Args:
        epic_id: ID of the existing epic.
        name: Story name.
        description: What needs to happen.
        phase: context|architecture|design|implementation|testing|security|review.
        assigned_titan: Which Titan executes this (e.g. "mnemos").
        sequence: Order within the epic.
        acceptance_criteria: Definition of done.
        depends_on_ids: Optional list of story IDs this depends on.
        conn: Kuzu connection (injected by Othrys).

    Returns: {added, story_id}
    """
    return _add_story(
        epic_id=epic_id,
        name=name,
        description=description,
        phase=phase,
        assigned_titan=assigned_titan,
        sequence=sequence,
        acceptance_criteria=acceptance_criteria,
        depends_on_ids=coerce(depends_on_ids, list),
        conn=conn,
    )


@mcp.tool()
def update_story(
    story_id: str,
    status: str | None = None,
    phase: str | None = None,
    output: Union[dict, str, None] = None,
    input_context: Union[dict, str, None] = None,
    store_as_memory: bool = False,
    memory_project: str = "",
    conn: Any = None,
) -> dict:
    """Update a story's status, phase, output, or input_context.

    The workhorse tool — called every time a story changes state.
    Prometheus calls this to mark stories in_progress, completed, etc.

    Args:
        story_id: ID of the story to update.
        status: New status: pending|in_progress|completed|blocked|failed.
        phase: New phase: context|architecture|design|implementation|
               testing|security|review|done.
        output: Titan's output for this story (dict or JSON string).
        input_context: Context passed to the Titan (dict or JSON string).
        store_as_memory: If True, create a memory node linked via produces.
        memory_project: Project name for the memory node.
        conn: Kuzu connection (injected by Othrys).

    Returns: {updated, story_id, fields_updated, memory_id}
    """
    return _update_story(
        story_id=story_id,
        status=status,
        phase=phase,
        output=coerce(output, dict),
        input_context=coerce(input_context, dict),
        store_as_memory=store_as_memory,
        memory_project=memory_project,
        conn=conn,
    )


@mcp.tool()
def get_plan(
    plan_id: str | None = None,
    conn: Any = None,
) -> dict:
    """Read a full execution plan with all epics and stories.

    If plan_id is None, returns the most recently created plan.
    The LLM uses this to figure out what's next, what's done,
    and what outputs are available as input_context.

    Args:
        plan_id: ID of the plan. None = latest plan.
        conn: Kuzu connection (injected by Othrys).

    Returns: {plan, epics: [{..., stories: [...]}], summary}
    """
    return _get_plan(plan_id=plan_id, conn=conn)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    mcp.run()


if __name__ == "__main__":
    main()
