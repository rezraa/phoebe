# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Add a story to an existing epic."""

from __future__ import annotations

from typing import Any

from phoebe.tools._shared import get_store, coerce
from phoebe.models import make_story


def add_story(
    epic_id: str,
    name: str,
    description: str,
    phase: str,
    assigned_titan: str,
    sequence: int,
    acceptance_criteria: str = "",
    depends_on_ids: list[str] | None = None,
    conn: Any = None,
) -> dict:
    """Add a story to an existing epic.

    Used for fix stories from adversarial review, or when Prometheus
    discovers new work is needed mid-execution.

    Args:
        epic_id: ID of the existing epic.
        name: Story name.
        description: What needs to happen.
        phase: context|architecture|design|implementation|testing|security|review.
        assigned_titan: Which Titan executes this (e.g. "mnemos").
        sequence: Order within the epic.
        acceptance_criteria: Definition of done.
        depends_on_ids: Optional list of story IDs this depends on.
        conn: Kuzu connection (Othrys mode) or None (standalone).

    Returns:
        {added: true, story_id}
    """
    store = get_store(conn)
    depends_on_ids = coerce(depends_on_ids, list) or []

    story = make_story(
        epic_id=epic_id,
        name=name,
        description=description,
        phase=phase,
        assigned_titan=assigned_titan,
        sequence=sequence,
        acceptance_criteria=acceptance_criteria,
    )
    story_id = store.add_story(story)
    store.link_epic_to_story(epic_id, story_id, sequence)

    if assigned_titan:
        try:
            store.link_story_to_agent(story_id, assigned_titan)
        except Exception:
            pass

    for dep_id in depends_on_ids:
        store.link_story_depends_on(story_id, dep_id)

    return {
        "added": True,
        "story_id": story_id,
    }
