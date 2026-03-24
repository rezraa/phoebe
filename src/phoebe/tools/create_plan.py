# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Create a full execution plan with epics and stories in Kuzu."""

from __future__ import annotations

import json
from typing import Any, Union

from phoebe.tools._shared import get_store, coerce
from phoebe.models import make_plan, make_epic, make_story


def create_plan(
    name: str,
    goal: str,
    epics: list[dict[str, Any]],
    conn: Any = None,
) -> dict:
    """Create a full execution plan with epics and stories.

    Creates plan, epic, and story nodes plus all relationships
    (has_epic, has_story, assigned_to, story_depends_on) in one call.

    Args:
        name: Plan name (e.g. "Build Theia Titan").
        goal: What the plan achieves.
        epics: List of epic dicts, each with:
            - name: Epic name
            - description: What this epic achieves
            - sequence: Order (1, 2, 3...)
            - acceptance_criteria: How we know it's done
            - stories: List of story dicts, each with:
                - name: Story name
                - description: What needs to happen
                - phase: context|architecture|design|implementation|testing|security|review
                - assigned_titan: Which Titan executes this (e.g. "mnemos")
                - sequence: Order within the epic
                - acceptance_criteria: Definition of done
                - depends_on: Optional list of story names this depends on
        conn: Kuzu connection (Othrys mode) or None (standalone).

    Returns:
        {created: true, plan_id, epic_ids: [...], story_ids: [...],
         edge_counts: {has_epic, has_story, assigned_to, depends_on}}
    """
    store = get_store(conn)
    epics = coerce(epics, list) or []

    # Create plan node
    plan = make_plan(name=name, goal=goal)
    plan_id = store.add_plan(plan)

    epic_ids = []
    story_ids = []
    edge_counts = {"has_epic": 0, "has_story": 0, "assigned_to": 0, "depends_on": 0}

    # Name → story_id map for resolving depends_on references
    story_name_to_id: dict[str, str] = {}
    # Deferred dependency links: [(story_id, depends_on_name)]
    deferred_deps: list[tuple[str, str]] = []

    for epic_data in epics:
        epic = make_epic(
            plan_id=plan_id,
            name=epic_data["name"],
            description=epic_data.get("description", ""),
            sequence=epic_data.get("sequence", 1),
            acceptance_criteria=epic_data.get("acceptance_criteria", ""),
        )
        epic_id = store.add_epic(epic)
        store.link_plan_to_epic(plan_id, epic_id, epic["sequence"])
        edge_counts["has_epic"] += 1
        epic_ids.append(epic_id)

        for story_data in epic_data.get("stories", []):
            story = make_story(
                epic_id=epic_id,
                name=story_data["name"],
                description=story_data.get("description", ""),
                phase=story_data.get("phase", "implementation"),
                assigned_titan=story_data.get("assigned_titan", ""),
                sequence=story_data.get("sequence", 1),
                acceptance_criteria=story_data.get("acceptance_criteria", ""),
            )
            story_id = store.add_story(story)
            store.link_epic_to_story(epic_id, story_id, story["sequence"])
            edge_counts["has_story"] += 1
            story_ids.append(story_id)
            story_name_to_id[story_data["name"]] = story_id

            # Assign to Titan
            if story_data.get("assigned_titan"):
                try:
                    store.link_story_to_agent(story_id, story_data["assigned_titan"])
                    edge_counts["assigned_to"] += 1
                except Exception:
                    pass  # Agent may not exist yet

            # Collect depends_on for deferred resolution
            for dep_name in story_data.get("depends_on", []):
                deferred_deps.append((story_id, dep_name))

    # Resolve story dependencies by name
    for story_id, dep_name in deferred_deps:
        dep_id = story_name_to_id.get(dep_name)
        if dep_id:
            store.link_story_depends_on(story_id, dep_id, reason=f"depends on {dep_name}")
            edge_counts["depends_on"] += 1

    return {
        "created": True,
        "plan_id": plan_id,
        "epic_ids": epic_ids,
        "story_ids": story_ids,
        "edge_counts": edge_counts,
    }
