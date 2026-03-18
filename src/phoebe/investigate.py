# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Investigate tool — autonomous research and knowledge building.

Given a topic, Phoebe crawls sources, extracts memories, builds the graph.
Additive and corrective — never deletes, only supersedes wrong data.
"""

from __future__ import annotations

import json
from typing import Any

from phoebe.store import GraphStore
from phoebe.reasoning import Reasoner
from phoebe.models import make_memory, make_source, make_entity, make_milestone


def investigate(
    topic: str,
    store: GraphStore,
    reasoner: Reasoner,
    search_fn: Any,
    fetch_fn: Any,
    project: str = "",
    depth: str = "standard",
) -> dict[str, Any]:
    """Autonomously research a topic and build/update the tome.

    This is Phoebe's core autonomous loop:
    1. Check what she already knows about the topic
    2. Search for sources
    3. Fetch and extract from each source
    4. Compare with existing knowledge — corroborate or contradict
    5. Add new memories, supersede wrong ones, never delete

    Args:
        topic: What to investigate
        store: GraphStore for the tome
        reasoner: Reasoner for the tome
        search_fn: Callable(query) -> list[{url, title, snippet}]
        fetch_fn: Callable(url, prompt) -> str (extracted content)
        project: Project name for scoping memories
        depth: "quick" (3 sources), "standard" (8), "deep" (15)

    Returns:
        Summary of what was found, added, corrected.
    """
    max_sources = {"quick": 3, "standard": 8, "deep": 15}.get(depth, 8)

    results = {
        "topic": topic,
        "existing_memories": 0,
        "sources_searched": 0,
        "sources_fetched": 0,
        "memories_added": 0,
        "memories_superseded": 0,
        "contradictions_found": 0,
        "corroborations_found": 0,
        "entities_added": 0,
        "errors": [],
    }

    # ── Step 1: Check existing knowledge ──────────────────────────
    existing = reasoner._execute(
        "MATCH (m:memories)-[:about]->(e:entities) "
        "WHERE e.name CONTAINS $topic AND m.status <> 'superseded' "
        "RETURN m, e.name",
        {"topic": topic},
    )
    results["existing_memories"] = len(existing)
    existing_claims = []
    for row in existing:
        mem = row[0]
        try:
            content = json.loads(mem["content"]) if isinstance(mem["content"], str) else mem["content"]
            existing_claims.append({
                "id": mem["id"],
                "content": content,
                "memory_type": mem["memory_type"],
                "confidence": mem.get("confidence", 0.5),
            })
        except (json.JSONDecodeError, TypeError):
            existing_claims.append({
                "id": mem["id"],
                "content": {"raw": mem.get("content", "")},
                "memory_type": mem["memory_type"],
                "confidence": mem.get("confidence", 0.5),
            })

    # ── Step 2: Search for sources ────────────────────────────────
    search_queries = [
        topic,
        f"{topic} decision history",
        f"{topic} technical details",
    ]
    if depth == "deep":
        search_queries.extend([
            f"{topic} controversy",
            f"{topic} alternatives considered",
        ])

    all_urls = []
    for query in search_queries:
        try:
            search_results = search_fn(query)
            for sr in search_results:
                url = sr.get("url", sr.get("link", ""))
                if url and url not in [u["url"] for u in all_urls]:
                    all_urls.append({"url": url, "title": sr.get("title", ""), "snippet": sr.get("snippet", "")})
        except Exception as e:
            results["errors"].append(f"Search error for '{query}': {str(e)}")
    results["sources_searched"] = len(all_urls)

    # ── Step 3: Fetch and extract from each source ────────────────
    extraction_prompt = f"""Extract ALL factual claims about "{topic}" from this content.
Return a JSON array of objects, each with:
- "claim": the factual statement (one sentence)
- "type": one of "decision", "context", "risk", "lesson", "observation", "assumption"
- "entities": list of key entity names mentioned (people, systems, projects)
- "confidence": 0.0-1.0 based on how authoritative this source is
- "date": date mentioned if any (ISO format), or null

ALSO check these existing claims and note if new content CONTRADICTS or CORROBORATES them:
{json.dumps(existing_claims[:10], indent=2, default=str)}

Add a "corrections" array of objects with:
- "existing_id": id of the existing claim
- "relationship": "contradicts" or "corroborates"
- "reason": why

Return ONLY valid JSON: {{"claims": [...], "corrections": [...]}}"""

    for source_info in all_urls[:max_sources]:
        url = source_info["url"]
        try:
            raw_extraction = fetch_fn(url, extraction_prompt)
            results["sources_fetched"] += 1
        except Exception as e:
            results["errors"].append(f"Fetch error for {url}: {str(e)}")
            continue

        # Parse extraction
        try:
            # Try to find JSON in the response
            extraction = _parse_json(raw_extraction)
            if not extraction:
                continue
        except Exception as e:
            results["errors"].append(f"Parse error for {url}: {str(e)}")
            continue

        # Register source
        src = make_source(
            uri=url,
            source_type="url",
            name=source_info.get("title", url.split("/")[-1]),
            extraction_model="claude",
        )
        source_id = store.get_or_create_source(src)

        # Process claims
        claims = extraction.get("claims", [])
        for claim in claims:
            if not claim.get("claim"):
                continue

            # Create memory
            mem = make_memory(
                content={"description": claim["claim"]},
                memory_type=claim.get("type", "observation"),
                project=project,
                confidence=claim.get("confidence", 0.7),
            )
            memory_id = store.add_memory(mem)
            store.link_memory_to_source(memory_id, source_id)
            results["memories_added"] += 1

            # Create/link entities
            for entity_name in claim.get("entities", []):
                ent = make_entity(name=entity_name, entity_type="system")
                eid = store.get_or_create_entity(ent)
                store.link_memory_to_entity(memory_id, eid, "about")
                results["entities_added"] += 1

            # Link to topic entity
            topic_ent = make_entity(name=topic, entity_type="decision")
            topic_eid = store.get_or_create_entity(topic_ent)
            store.link_memory_to_entity(memory_id, topic_eid, "about")

        # Process corrections
        corrections = extraction.get("corrections", [])
        for correction in corrections:
            existing_id = correction.get("existing_id", "")
            relationship = correction.get("relationship", "")
            reason = correction.get("reason", "")

            if not existing_id or not relationship:
                continue

            # Find the most recent memory we added about this topic as the correcting memory
            recent = store.query_memories(project=project, limit=1)
            if not recent:
                continue
            new_id = recent[0]["id"]

            if relationship == "contradicts":
                # Create correction memory, supersede the old one, link contradiction
                correction_mem = make_memory(
                    content={"description": f"CORRECTION: {reason}", "corrects": existing_id},
                    memory_type="observation",
                    project=project,
                    confidence=0.9,
                )
                correction_id = correction_mem["id"]
                # supersede_memory handles insert + status change + edge
                store.supersede_memory(existing_id, correction_mem, reason)
                store.link_memory_to_source(correction_id, source_id)
                store.link_memories_contradict(correction_id, existing_id, reason)
                results["memories_superseded"] += 1
                results["contradictions_found"] += 1

            elif relationship == "corroborates":
                store.link_memories_corroborate(new_id, existing_id)
                results["corroborations_found"] += 1

    return results


def _parse_json(text: str) -> dict | None:
    """Try to extract JSON from a text response."""
    # Try direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # Try to find JSON block in markdown
    import re
    patterns = [
        r'```json\s*(.*?)\s*```',
        r'```\s*(.*?)\s*```',
        r'\{.*\}',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1) if '```' in pattern else match.group(0))
            except (json.JSONDecodeError, TypeError):
                continue
    return None
