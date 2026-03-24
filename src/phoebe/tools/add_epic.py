# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Add an epic to an existing plan."""

from __future__ import annotations

from typing import Any

from phoebe.tools._shared import get_store, coerce
from phoebe.models import make_epic, make_story


def add_epic(
    plan_id: str,
    name: str,
    description: str,
    sequence: int,
    acceptance_criteria: str = "",
    stories: list[dict[str, Any]] | None = None,
    conn: Any = None,
) -> dict:
    """Add an epic (and optional stories) to an existing plan.

    Used when Prometheus adds scope mid-execution — new epics that
    weren't in the original plan.

    Args:
        plan_id: ID of the existing plan.
        name: Epic name.
        description: What this epic achieves.
        sequence: Order within the plan.
        acceptance_criteria: How we know it's done.
        stories: Optional list of story dicts (same format as create_plan).
        conn: Kuzu connection (Othrys mode) or None (standalone).

    Returns:
        {added: true, epic_id, story_ids: [...]}
    """
    store = get_store(conn)
    stories = coerce(stories, list) or []

    epic = make_epic(
        plan_id=plan_id,
        name=name,
        description=description,
        sequence=sequence,
        acceptance_criteria=acceptance_criteria,
    )
    epic_id = store.add_epic(epic)
    store.link_plan_to_epic(plan_id, epic_id, sequence)

    story_ids = []
    for story_data in stories:
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
        story_ids.append(story_id)

        if story_data.get("assigned_titan"):
            try:
                store.link_story_to_agent(story_id, story_data["assigned_titan"])
            except Exception:
                pass

    return {
        "added": True,
        "epic_id": epic_id,
        "story_ids": story_ids,
    }
