# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Update a story's status, phase, output, or input_context."""

from __future__ import annotations

from typing import Any, Union

from phoebe._codec import json_encode
from phoebe.tools._shared import get_store, coerce_str_or_container
from phoebe.models import make_memory


def update_story(
    story_id: str,
    status: str | None = None,
    phase: str | None = None,
    output: Union[dict[str, Any], str, None] = None,
    input_context: Union[dict[str, Any], str, None] = None,
    acceptance_criteria: str | None = None,
    store_as_memory: bool | None = None,
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
        acceptance_criteria: Updated acceptance criteria for the story.
        store_as_memory: If True, also create a memory node linked via
                         produces edge. Defaults to True when status is
                         "completed" (or "done"), False otherwise. Pass
                         False explicitly to opt out even on completion.
                         The artifact-memory inherits its project from the
                         story's own plan (story -> epic -> plan.project);
                         there is no project parameter — the parent chain
                         scopes it unambiguously, even cross-project.
        conn: Kuzu connection (Othrys mode) or None (standalone).

    Returns:
        {updated: true, story_id, fields_updated: [...], memory_id: "..." or null}
    """
    store = get_store(conn)
    output = coerce_str_or_container(output, dict)
    input_context = coerce_str_or_container(input_context, dict)

    fields: dict[str, Any] = {}
    fields_updated: list[str] = []

    if status is not None:
        # Normalize common aliases so the GUI always sees canonical values
        _STATUS_ALIASES = {"done": "completed"}
        fields["status"] = _STATUS_ALIASES.get(status, status)
        fields_updated.append("status")

    # Auto-enable memory persistence when a story is completed,
    # unless the caller explicitly opted out (store_as_memory=False).
    if store_as_memory is None:
        store_as_memory = fields.get("status") == "completed"

    if phase is not None:
        fields["phase"] = phase
        fields_updated.append("phase")
    if output is not None:
        fields["output"] = json_encode(output) if isinstance(output, dict) else output
        fields_updated.append("output")
    if input_context is not None:
        fields["input_context"] = json_encode(input_context) if isinstance(input_context, dict) else input_context
        fields_updated.append("input_context")
    if acceptance_criteria is not None:
        fields["acceptance_criteria"] = acceptance_criteria
        fields_updated.append("acceptance_criteria")

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
            # The artifact inherits the story's plan project (story -> epic ->
            # plan.project); the parent chain scopes it, not any caller param.
            project=store.get_project_for_story(story_id),
        )
        memory_id = store.add_memory(mem)
        store.link_story_produces(story_id, memory_id)

    return {
        "updated": True,
        "story_id": story_id,
        "fields_updated": fields_updated,
        "memory_id": memory_id,
    }
