# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Store a memory with source reference and entity links."""

from __future__ import annotations

from typing import Any, Union

from phoebe.tools._shared import get_store, coerce, make_memory, make_source, make_entity, make_milestone


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
    conn: Any = None,
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
        conn: Kuzu connection (Othrys mode) or None (standalone mode).

    Returns: {stored: true, memory_id, source_id, entities}
    """
    store = get_store(conn)
    entities_list = coerce(entities, list) or []

    # Dedup: check if a memory with the same content already exists
    import json
    content_json = json.dumps({"description": content})
    existing = store.query_memories(project=project or None, limit=50)
    for ex in existing:
        if ex.get("content") == content_json:
            return {
                "stored": False,
                "memory_id": ex["id"],
                "source_id": "",
                "entities": [],
                "note": "duplicate — already in tome",
            }

    mem = make_memory(
        content={"description": content},
        memory_type=memory_type,
        project=project or "",
        confidence=confidence,
        status=status,
        outcome=outcome,
    )
    memory_id = store.add_memory(mem)

    source_id = ""
    if source_uri:
        src = make_source(uri=source_uri, source_type=source_type)
        source_id = store.get_or_create_source(src)
        store.link_memory_to_source(memory_id, source_id)

    entity_ids = []
    for name in entities_list:
        ent = make_entity(name=name, entity_type="system")
        eid = store.get_or_create_entity(ent)
        store.link_memory_to_entity(memory_id, eid, "about")
        entity_ids.append(eid)

    if milestone and milestone.strip():
        ms = make_milestone(name=milestone, milestone_type="sprint")
        ms_id = store.get_or_create_milestone(ms)
        store.link_memory_to_milestone(memory_id, ms_id)

    if caused_by_id:
        store.link_memory_caused_by(memory_id, caused_by_id)

    return {
        "stored": True,
        "memory_id": memory_id,
        "source_id": source_id,
        "entities": entity_ids,
    }
