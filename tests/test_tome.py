# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Tests for Phoebe's tome, store, and reasoning."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from phoebe.tome import Tome
from phoebe.store import GraphStore
from phoebe.reasoning import Reasoner
from phoebe.models import make_memory, make_source, make_entity, make_milestone


@pytest.fixture
def tome(tmp_path):
    """Create a temporary tome for testing."""
    tome_path = tmp_path / "test.tome"
    t = Tome(tome_path)
    t.open()
    yield t
    t.close()


@pytest.fixture
def store(tome):
    return GraphStore(tome.connection())


@pytest.fixture
def reasoner(tome):
    return Reasoner(tome.connection())


# ------------------------------------------------------------------
# Tome basics
# ------------------------------------------------------------------

class TestTome:
    def test_create_and_open(self, tmp_path):
        path = tmp_path / "new.tome"
        assert not path.exists()
        with Tome(path) as t:
            assert path.exists()
            s = t.stats()
            assert s["memories"] == 0
            assert s["sources"] == 0
            assert s["entities"] == 0
            assert s["milestones"] == 0

    def test_context_manager(self, tmp_path):
        path = tmp_path / "ctx.tome"
        with Tome(path) as t:
            conn = t.connection()
            assert conn is not None


# ------------------------------------------------------------------
# Store CRUD
# ------------------------------------------------------------------

class TestStore:
    def test_add_and_get_memory(self, store):
        mem = make_memory(
            content={"description": "chose Postgres for ACID compliance"},
            memory_type="decision",
            project="test-project",
        )
        mid = store.add_memory(mem)
        assert mid == mem["id"]

        retrieved = store.get_memory(mid)
        assert retrieved is not None

    def test_query_memories_by_project(self, store):
        for i in range(3):
            store.add_memory(make_memory(
                content={"n": i},
                memory_type="observation",
                project="alpha",
            ))
        store.add_memory(make_memory(
            content={"n": 99},
            memory_type="observation",
            project="beta",
        ))

        alpha = store.query_memories(project="alpha")
        assert len(alpha) == 3

        beta = store.query_memories(project="beta")
        assert len(beta) == 1

    def test_add_and_find_source(self, store):
        src = make_source(uri="slack://eng/auth-thread", source_type="slack")
        sid = store.add_source(src)
        assert sid

        found = store.find_source_by_uri("slack://eng/auth-thread")
        assert found is not None

        not_found = store.find_source_by_uri("slack://eng/nonexistent")
        assert not_found is None

    def test_get_or_create_source_deduplicates(self, store):
        src = make_source(uri="https://example.com/doc", source_type="url")
        id1 = store.get_or_create_source(src)
        id2 = store.get_or_create_source(make_source(uri="https://example.com/doc", source_type="url"))
        assert id1 == id2

    def test_add_and_find_entity(self, store):
        ent = make_entity(name="auth-service", entity_type="service")
        eid = store.add_entity(ent)
        assert eid

        found = store.find_entity_by_name("auth-service")
        assert found is not None

    def test_get_or_create_entity_deduplicates(self, store):
        ent = make_entity(name="redis", entity_type="system")
        id1 = store.get_or_create_entity(ent)
        id2 = store.get_or_create_entity(make_entity(name="redis", entity_type="system"))
        assert id1 == id2

    def test_add_milestone(self, store):
        ms = make_milestone(name="sprint-14", milestone_type="sprint")
        mid = store.add_milestone(ms)
        assert mid

        found = store.find_milestone_by_name("sprint-14")
        assert found is not None

    def test_supersede_memory(self, store):
        old = make_memory(content={"v": 1}, memory_type="decision", project="p")
        old_id = store.add_memory(old)

        new = make_memory(content={"v": 2}, memory_type="decision", project="p")
        new_id = store.supersede_memory(old_id, new, "requirements changed")

        old_mem = store.get_memory(old_id)
        assert old_mem["status"] == "superseded"

    def test_mark_source_stale(self, store):
        src = make_source(uri="https://deleted.com/page", source_type="url")
        sid = store.add_source(src)

        store.mark_source_stale(sid)
        stale = store.get_stale_sources()
        assert len(stale) == 1
        assert stale[0]["uri"] == "https://deleted.com/page"


# ------------------------------------------------------------------
# Edge creation
# ------------------------------------------------------------------

class TestEdges:
    def test_memory_to_source(self, store):
        mem = make_memory(content={"x": 1}, memory_type="observation", project="p")
        mid = store.add_memory(mem)
        src = make_source(uri="file:///doc.md", source_type="file")
        sid = store.add_source(src)

        store.link_memory_to_source(mid, sid)
        # Verify via query
        conn = store._conn
        result = conn.execute(
            "MATCH (m:memories)-[:extracted_from]->(s:sources) "
            "WHERE m.id = $mid RETURN s.uri",
            parameters={"mid": mid},
        )
        row = result.get_next()
        assert row[0] == "file:///doc.md"

    def test_memory_to_entity(self, store):
        mem = make_memory(content={"x": 1}, memory_type="decision", project="p")
        mid = store.add_memory(mem)
        ent = make_entity(name="postgres", entity_type="system")
        eid = store.add_entity(ent)

        store.link_memory_to_entity(mid, eid, "about")

    def test_entity_depends_on(self, store):
        svc_a = make_entity(name="api-gateway", entity_type="service")
        svc_b = make_entity(name="auth-service", entity_type="service")
        id_a = store.add_entity(svc_a)
        id_b = store.add_entity(svc_b)

        store.link_entity_depends_on(id_a, id_b, "authentication")

    def test_causal_chain(self, store):
        cause = make_memory(content={"desc": "compliance flag"}, memory_type="risk", project="p")
        effect = make_memory(content={"desc": "chose event sourcing"}, memory_type="decision", project="p")
        cid = store.add_memory(cause)
        eid = store.add_memory(effect)

        store.link_memory_caused_by(eid, cid, "compliance requirement")


# ------------------------------------------------------------------
# Reasoning
# ------------------------------------------------------------------

class TestReasoning:
    def test_blast_radius(self, store, reasoner):
        redis = make_entity(name="redis", entity_type="system")
        cache = make_entity(name="cache-service", entity_type="service")
        session = make_entity(name="session-store", entity_type="service")

        rid = store.add_entity(redis)
        cid = store.add_entity(cache)
        sid = store.add_entity(session)

        store.link_entity_depends_on(cid, rid, "caching")
        store.link_entity_depends_on(sid, rid, "session storage")

        result = reasoner.blast_radius("redis")
        assert result["dependent_count"] == 2

    def test_open_questions(self, store, reasoner):
        store.add_memory(make_memory(
            content={"q": "should we split auth?"},
            memory_type="question",
            status="open",
            project="p",
        ))
        store.add_memory(make_memory(
            content={"q": "resolved: yes split it"},
            memory_type="question",
            status="resolved",
            project="p",
        ))

        open_qs = reasoner.open_questions("p")
        assert len(open_qs) == 1

    def test_failed_approaches(self, store, reasoner):
        store.add_memory(make_memory(
            content={"desc": "sliding window rate limiter"},
            memory_type="lesson",
            outcome="failure",
            project="p",
        ))
        store.add_memory(make_memory(
            content={"desc": "token bucket worked"},
            memory_type="lesson",
            outcome="success",
            project="p",
        ))

        failed = reasoner.failed_approaches("p")
        assert len(failed) == 1

    def test_context_brief(self, store, reasoner):
        store.add_memory(make_memory(
            content={"desc": "chose Postgres"},
            memory_type="decision",
            status="resolved",
            project="myapp",
        ))
        store.add_memory(make_memory(
            content={"q": "microservices?"},
            memory_type="question",
            status="open",
            project="myapp",
        ))

        b = reasoner.context_brief("myapp")
        assert b["project"] == "myapp"
        assert len(b["recent_decisions"]) == 1
        assert len(b["open_questions"]) == 1

    def test_stale_source_impact(self, store, reasoner):
        src = make_source(uri="https://gone.com", source_type="url")
        sid = store.add_source(src)
        store.mark_source_stale(sid)

        mem = make_memory(content={"x": 1}, memory_type="observation", project="p")
        mid = store.add_memory(mem)
        store.link_memory_to_source(mid, sid)

        impact = reasoner.stale_source_impact()
        assert len(impact) == 1
        assert impact[0]["memories_at_risk"] == 1
