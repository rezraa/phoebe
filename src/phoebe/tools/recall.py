# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Query memories from the tome by topic, project, type, or entity."""

from __future__ import annotations

from typing import Any

from phoebe.tools._shared import get_store, get_reasoner


def recall(
    query: str,
    project: str | None = None,
    memory_type: str | None = None,
    entity: str | None = None,
    status: str | None = None,
    limit: int = 20,
    conn: Any = None,
) -> dict:
    """Query memories from the tome by topic, project, type, or entity.

    Args:
        query: Topic to search for in entity names and memory content.
        project: Optional filter by project name.
        memory_type: Optional filter by type.
        entity: Optional filter by specific entity name.
        status: Optional filter by status.
        limit: Max results to return.
        conn: Kuzu connection (Othrys mode) or None (standalone mode).

    Returns: {memories: [...], count: N}
    """
    store = get_store(conn)
    reasoner = get_reasoner(conn)

    if entity:
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
        params = {"query": query}
        seen = set()
        memories = []

        # BM25 full-text search
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
            pass

        memories = memories[:limit]
    else:
        memories = store.query_memories(
            project=project or None,
            memory_type=memory_type or None,
            status=status or None,
            limit=limit,
        )

    return {"memories": memories, "count": len(memories)}
