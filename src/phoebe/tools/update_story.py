# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Update a story's status, phase, output, or input_context."""

from __future__ import annotations

import json
from typing import Any, Union

from phoebe.tools._shared import get_store, coerce
from phoebe.models import make_memory


def update_story(
    story_id: str,
    status: str | None = None,
    phase: str | None = None,
    output: Union[dict[str, Any], str, None] = None,
    input_context: Union[dict[str, Any], str, None] = None,
    store_as_memory: bool = False,
    memory_project: str = "",
    conn: Any = None,
) -> dict:
    """Update a story's fields.

    This is the workhorse tool — called every time a story changes state.
    Prometheus calls this to mark stories in_progress, completed, failed,
    or blocked, and to store Titan outputs.

    Args:
        story_id: ID of the story to update.
        status: New status: pending|in_progress|completed|blocked|failed.
        phase: New phase: context|architecture|design|implementation|
               testing|security|review|done.
        output: Titan's output for this story (dict or JSON string).
        input_context: Context passed to the Titan (dict or JSON string).
        store_as_memory: If True, also create a memory node linked via
                         produces edge. Use when the output is an artifact
                         worth remembering (design spec, test results, etc.).
        memory_project: Project name for the memory node.
        conn: Kuzu connection (Othrys mode) or None (standalone).

    Returns:
        {updated: true, story_id, fields_updated: [...], memory_id: "..." or null}
    """
    store = get_store(conn)
    output = coerce(output, dict)
    input_context = coerce(input_context, dict)

    fields: dict[str, Any] = {}
    fields_updated: list[str] = []

    if status is not None:
        fields["status"] = status
        fields_updated.append("status")
    if phase is not None:
        fields["phase"] = phase
        fields_updated.append("phase")
    if output is not None:
        fields["output"] = json.dumps(output) if isinstance(output, dict) else output
        fields_updated.append("output")
    if input_context is not None:
        fields["input_context"] = json.dumps(input_context) if isinstance(input_context, dict) else input_context
        fields_updated.append("input_context")

    if fields:
        store.update_story(story_id, **fields)

    # Optionally persist output as a memory (artifact)
    memory_id = None
    if store_as_memory and output:
        story = store.get_story(story_id)
        story_name = story.get("name", story_id) if story else story_id
        mem = make_memory(
            content={"story": story_name, "artifact": output},
            memory_type="context",
            agent=story.get("assigned_titan", "unknown") if story else "unknown",
            project=memory_project,
        )
        memory_id = store.add_memory(mem)
        store.link_story_produces(story_id, memory_id)

    return {
        "updated": True,
        "story_id": story_id,
        "fields_updated": fields_updated,
        "memory_id": memory_id,
    }
