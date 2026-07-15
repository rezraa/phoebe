# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Update an epic's status and/or stored output."""

from __future__ import annotations

from typing import Any, Union

from phoebe._codec import json_decode, json_encode
from phoebe.tools._shared import get_store, coerce_str_or_container


def update_epic(
    epic_id: str,
    status: str | None = None,
    output: Union[dict[str, Any], str, None] = None,
    *,
    conn: Any = None,
) -> dict:
    """Update an epic's status and/or stored output.

    Mirrors ``update_story``: looks up the epic by id, updates only the
    provided fields, and returns the same shape. The epic schema has no
    dedicated ``output`` column, so ``output`` is merged into the
    ``data`` JSON blob under the ``output`` key.

    Args:
        epic_id: ID of the epic to update.
        status: New status (e.g. planned|in_progress|completed|failed).
        output: Titan/council output to persist on the epic (dict or JSON
                string). Stored inside epics.data under the "output" key.
        conn: Kuzu connection (Othrys mode) or None (standalone).

    Returns:
        {updated: true, epic_id, fields_updated: [...]}
    """
    store = get_store(conn)
    output = coerce_str_or_container(output, dict)

    fields: dict[str, Any] = {}
    fields_updated: list[str] = []

    if status is not None:
        fields["status"] = status
        fields_updated.append("status")

    if output is not None:
        # Fetch existing data blob, merge the output under the "output" key.
        existing_data: dict[str, Any] = {}
        rows = store._execute(
            "MATCH (e:epics) WHERE e.id = $id RETURN e.data",
            {"id": epic_id},
        )
        if rows:
            parsed = json_decode(rows[0][0])
            if isinstance(parsed, dict):
                existing_data = parsed

        existing_data["output"] = output
        fields["data"] = json_encode(existing_data)
        fields_updated.append("output")

    if fields:
        store.update_epic(epic_id, **fields)

    return {
        "updated": True,
        "epic_id": epic_id,
        "fields_updated": fields_updated,
    }
