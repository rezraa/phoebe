"""Phoebe's embedded Kuzu graph schema.

Memories are the core — references to sources + structured extractions.
No blobs. No file copies. Just memories and the edges between them.

Design principle: the graph should answer WHY, WHEN, WHO, WHAT DEPENDS,
and WHAT CHANGED — not just WHAT.
"""

SCHEMA = [
    # ──────────────────────────────────────────────
    # NODE TABLES
    # ──────────────────────────────────────────────

    # Memories — what Phoebe learned (provenance tracked via extracted_from → sources)
    # Fields: content (JSON extraction), memory_type, status, outcome, agent, project, confidence
    """CREATE NODE TABLE IF NOT EXISTS memories (
        id STRING,
        content STRING,
        memory_type STRING,
        status STRING,
        outcome STRING,
        agent STRING,
        project STRING,
        confidence FLOAT,
        timestamp STRING,
        PRIMARY KEY(id)
    )""",

    # Entities — things Phoebe has learned about
    # entity_type: person, team, system, service, component, pattern, decision, project, tool, library, api, config
    """CREATE NODE TABLE IF NOT EXISTS entities (
        id STRING,
        name STRING,
        entity_type STRING,
        data STRING,
        PRIMARY KEY(id)
    )""",

    # Sources — where Phoebe learned things (deduplicated, trackable)
    # source_type: slack, gdrive, confluence, file, url, meeting, conversation, code, github_pr, github_issue, jira, email
    """CREATE NODE TABLE IF NOT EXISTS sources (
        id STRING,
        uri STRING,
        source_type STRING,
        name STRING,
        last_crawled STRING,
        last_verified STRING,
        stale BOOLEAN,
        extraction_model STRING,
        data STRING,
        PRIMARY KEY(id)
    )""",

    # Milestones — temporal anchors
    # milestone_type: sprint, release, version, incident, migration, deadline
    # status: planned, active, completed, cancelled
    """CREATE NODE TABLE IF NOT EXISTS milestones (
        id STRING,
        name STRING,
        milestone_type STRING,
        start_date STRING,
        end_date STRING,
        status STRING,
        data STRING,
        PRIMARY KEY(id)
    )""",

    # ──────────────────────────────────────────────
    # MEMORY ↔ MEMORY EDGES (causal chains)
    # ──────────────────────────────────────────────

    # Why did this happen?
    "CREATE REL TABLE IF NOT EXISTS caused_by (FROM memories TO memories, reason STRING)",

    # Is this still current?
    "CREATE REL TABLE IF NOT EXISTS supersedes (FROM memories TO memories, reason STRING)",

    # Do sources agree or conflict?
    "CREATE REL TABLE IF NOT EXISTS contradicts (FROM memories TO memories, resolution STRING)",
    "CREATE REL TABLE IF NOT EXISTS corroborates (FROM memories TO memories)",

    # What's blocking what?
    "CREATE REL TABLE IF NOT EXISTS blocked_by (FROM memories TO memories, reason STRING)",

    # ──────────────────────────────────────────────
    # MEMORY ↔ SOURCE EDGES (provenance)
    # ──────────────────────────────────────────────

    # Where did this memory come from?
    "CREATE REL TABLE IF NOT EXISTS extracted_from (FROM memories TO sources)",

    # ──────────────────────────────────────────────
    # SOURCE ↔ SOURCE EDGES (hierarchy)
    # ──────────────────────────────────────────────

    # Source containment (workspace → channel, space → page, repo → PR)
    "CREATE REL TABLE IF NOT EXISTS contains (FROM sources TO sources)",

    # ──────────────────────────────────────────────
    # MEMORY ↔ ENTITY EDGES (who, what, where)
    # ──────────────────────────────────────────────

    # What is this memory about?
    "CREATE REL TABLE IF NOT EXISTS about (FROM memories TO entities)",

    # Who decided / authored this?
    "CREATE REL TABLE IF NOT EXISTS decided_by (FROM memories TO entities)",

    # What systems/services does this affect?
    "CREATE REL TABLE IF NOT EXISTS affects (FROM memories TO entities)",

    # ──────────────────────────────────────────────
    # MEMORY ↔ MILESTONE EDGES (when)
    # ──────────────────────────────────────────────

    # When did this happen?
    "CREATE REL TABLE IF NOT EXISTS occurred_during (FROM memories TO milestones)",

    # ──────────────────────────────────────────────
    # ENTITY ↔ ENTITY EDGES (dependencies, ownership, expertise)
    # ──────────────────────────────────────────────

    # Generic relationship
    "CREATE REL TABLE IF NOT EXISTS related_to (FROM entities TO entities, relationship STRING)",

    # What breaks if I change this? System/service dependency graph.
    "CREATE REL TABLE IF NOT EXISTS depends_on (FROM entities TO entities, dependency_type STRING)",

    # Who owns / maintains this?
    "CREATE REL TABLE IF NOT EXISTS owns (FROM entities TO entities, role STRING)",

    # ──────────────────────────────────────────────
    # ENTITY ↔ MILESTONE EDGES (lifecycle)
    # ──────────────────────────────────────────────

    # When was this entity introduced / changed / deprecated?
    "CREATE REL TABLE IF NOT EXISTS introduced_in (FROM entities TO milestones)",
    "CREATE REL TABLE IF NOT EXISTS deprecated_in (FROM entities TO milestones)",
]


# ──────────────────────────────────────────────
# EXAMPLE QUERIES THIS SCHEMA ANSWERS
# ──────────────────────────────────────────────
#
# "What happened last sprint?"
#   MATCH (m:memories)-[:occurred_during]->(ms:milestones {name: 'sprint-14'})
#   RETURN m ORDER BY m.timestamp
#
# "Why did we choose Postgres?"
#   MATCH (m:memories)-[:about]->(e:entities {name: 'postgres'})
#   WHERE m.memory_type = 'decision'
#   MATCH (m)-[:caused_by]->(reason:memories)
#   RETURN m, reason
#
# "What breaks if we change the payment service?"
#   MATCH (e:entities {name: 'payment-service'})<-[:depends_on]-(dep:entities)
#   RETURN dep
#
# "Who owns billing?"
#   MATCH (person:entities)-[:owns]->(e:entities {name: 'billing'})
#   RETURN person
#
# "Who knows the most about auth?"
#   MATCH (m:memories)-[:about]->(e:entities {name: 'auth'})
#   MATCH (m)-[:decided_by]->(person:entities {entity_type: 'person'})
#   RETURN person.name, COUNT(m) AS expertise ORDER BY expertise DESC
#
# "Is the auth migration decision still current?"
#   MATCH (m:memories)-[:about]->(e:entities {name: 'auth'})
#   WHERE m.memory_type = 'decision'
#   OPTIONAL MATCH (newer:memories)-[:supersedes]->(m)
#   RETURN m, newer
#
# "What changed between v2 and v3?"
#   MATCH (m:memories)-[:occurred_during]->(ms:milestones)
#   WHERE ms.name IN ['v2.0', 'v3.0']
#   RETURN ms.name, COLLECT(m)
#
# "Is this a recurring problem?"
#   MATCH (m:memories)-[:about]->(e:entities {name: 'deploy-pipeline'})
#   WHERE m.memory_type = 'incident'
#   RETURN COUNT(m), COLLECT(m.timestamp)
#
# "When was Redis introduced?"
#   MATCH (e:entities {name: 'redis'})-[:introduced_in]->(ms:milestones)
#   RETURN ms
#
# "What depends on Redis and was it affected by the Sprint 12 incident?"
#   MATCH (dep:entities)-[:depends_on]->(e:entities {name: 'redis'})
#   MATCH (m:memories)-[:affects]->(dep)
#   MATCH (m)-[:occurred_during]->(ms:milestones {name: 'sprint-12'})
#   WHERE m.memory_type = 'incident'
#   RETURN dep, m
#
# "What did we try that failed?"
#   MATCH (m:memories) WHERE m.outcome = 'failure' RETURN m
#
# "What's blocked right now?"
#   MATCH (m:memories)-[:blocked_by]->(blocker:memories)
#   WHERE m.status = 'open'
#   RETURN m, blocker
#
# "What's undecided / still open?"
#   MATCH (m:memories) WHERE m.status = 'open' AND m.memory_type IN ['decision', 'question']
#   RETURN m ORDER BY m.timestamp
#
# "What assumptions are we making?"
#   MATCH (m:memories) WHERE m.memory_type = 'assumption' AND m.status != 'superseded'
#   RETURN m
#
# "How has auth evolved over time?"
#   MATCH (m:memories)-[:about]->(e:entities {name: 'auth'})
#   MATCH (m)-[:occurred_during]->(ms:milestones)
#   RETURN m, ms ORDER BY ms.start_date
#
# "Where did we learn about the Postgres decision?"
#   MATCH (m:memories)-[:about]->(e:entities {name: 'postgres'})
#   WHERE m.memory_type = 'decision'
#   MATCH (m)-[:extracted_from]->(s:sources)
#   RETURN m, s.uri, s.source_type
#
# "What sources are stale? What did we learn from them?"
#   MATCH (s:sources) WHERE s.stale = true
#   MATCH (m:memories)-[:extracted_from]->(s)
#   RETURN s.uri, COUNT(m) AS memories_at_risk
#
# "Re-crawl all Slack sources"
#   MATCH (s:sources) WHERE s.source_type = 'slack'
#   RETURN s.uri, s.last_crawled
#
# "What did we learn from the Sprint 14 retro meeting?"
#   MATCH (m:memories)-[:extracted_from]->(s:sources {name: 'sprint-14-retro'})
#   RETURN m


def init_schema(conn) -> None:
    """Initialize Phoebe's graph schema and FTS index."""
    for stmt in SCHEMA:
        conn.execute(stmt)

    # Load FTS extension and create BM25 index on memory content
    try:
        conn.execute("LOAD EXTENSION fts")
        conn.execute("CALL CREATE_FTS_INDEX('memories', 'memory_search', ['content'])")
    except Exception:
        pass  # Index may already exist, or extension not available
