# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Query memories from the tome by topic, project, type, or entity."""

from __future__ import annotations

import logging
from typing import Any

from phoebe.store import _MEMORY_STORED_COLS
from phoebe.tools._shared import get_store

log = logging.getLogger(__name__)


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

    if entity:
        # Entity-scoped walk. Every filter is pushed INTO the query and
        # ``limit`` is BOUND (never f-string-interpolated, CWE-943). Explicit
        # stored-column projection drops the driver's _ID/_LABEL pointers.
        conditions = ["e.name = $entity"]
        params: dict = {"entity": entity, "limit": limit}
        if project:
            conditions.append("m.project = $project")
            params["project"] = project
        if memory_type:
            conditions.append("m.memory_type = $memory_type")
            params["memory_type"] = memory_type
        if status:
            conditions.append("m.status = $status")
            params["status"] = status
        where = " AND ".join(conditions)
        memories = store._project(
            match=f"MATCH (m:memories)-[:about]->(e:entities) WHERE {where}",
            alias="m",
            cols=_MEMORY_STORED_COLS,
            params=params,
            order=" ORDER BY m.timestamp DESC LIMIT $limit",
        )
    elif query:
        # BM25 full-text search. project / memory_type / status are pushed INTO
        # the query (WHERE on the FTS-returned node) so filtering happens
        # BEFORE LIMIT — post-filtering after LIMIT silently under-returns.
        # ``limit`` is BOUND. An FTS failure is LOGGED and degrades to the
        # structured filter path, never a silent empty (which is
        # indistinguishable from "no matches").
        fts_where: list[str] = []
        fts_params: dict = {"query": query, "limit": limit}
        if project:
            fts_where.append("node.project = $project")
            fts_params["project"] = project
        if memory_type:
            fts_where.append("node.memory_type = $memory_type")
            fts_params["memory_type"] = memory_type
        if status:
            fts_where.append("node.status = $status")
            fts_params["status"] = status
        where_clause = (" WHERE " + " AND ".join(fts_where)) if fts_where else ""
        try:
            fts_rows = store._execute(
                "CALL QUERY_FTS_INDEX('memories', 'memory_search', $query)"
                f"{where_clause} "
                "RETURN node, score ORDER BY score DESC LIMIT $limit",
                fts_params,
            )
        except Exception as exc:
            log.warning(
                "recall: FTS query failed (%s); falling back to structured "
                "filter so recall stays sound (not a silent empty)", exc,
            )
            memories = store.query_memories(
                project=project or None,
                memory_type=memory_type or None,
                status=status or None,
                limit=limit,
            )
        else:
            seen: set = set()
            memories = []
            for r in fts_rows:
                node = r[0]
                mid = node.get("id", "")
                if not mid or mid in seen:
                    continue
                seen.add(mid)
                # Project to stored columns — drops _ID/_LABEL, keeps id.
                memories.append({c: node.get(c) for c in _MEMORY_STORED_COLS})
    else:
        memories = store.query_memories(
            project=project or None,
            memory_type=memory_type or None,
            status=status or None,
            limit=limit,
        )

    return {"memories": memories, "count": len(memories)}
