# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""A/B test: Phoebe investigates Python GIL removal.

Seeds the tome with deliberately wrong data, then lets Phoebe investigate
using real web sources. She should:
- Find new information and add it
- Detect contradictions with seeded bad data
- Supersede wrong memories (never delete)
- Corroborate correct information
- Build entity graph and causal chains

Run with: PYTHONPATH=src .venv/bin/pytest tests/test_ab_investigate.py -v -s
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from phoebe.tome import Tome
from phoebe.store import GraphStore
from phoebe.reasoning import Reasoner
from phoebe.models import make_memory, make_source, make_entity
from phoebe.investigate import investigate


# ── Bad data to seed ──────────────────────────────────────────────
# These are deliberately wrong claims about PEP 703 / Python GIL removal

BAD_SEEDS = [
    {
        "content": {"description": "PEP 703 was rejected by the Python Steering Council in 2023"},
        "memory_type": "decision",
        "confidence": 0.7,
        "source_uri": "https://old-blog.example.com/python-gil-rejected",
        "entities": ["PEP 703", "Python Steering Council", "Python GIL removal"],
    },
    {
        "content": {"description": "Guido van Rossum proposed removing the GIL in PEP 703"},
        "memory_type": "context",
        "confidence": 0.6,
        "source_uri": "https://old-blog.example.com/guido-gil",
        "entities": ["Guido van Rossum", "PEP 703", "Python GIL removal"],
    },
    {
        "content": {"description": "The nogil approach completely removes reference counting and uses tracing garbage collection instead"},
        "memory_type": "context",
        "confidence": 0.5,
        "source_uri": "https://old-blog.example.com/nogil-gc",
        "entities": ["nogil", "Python GIL removal", "reference counting"],
    },
    {
        "content": {"description": "Free-threaded Python has zero performance overhead compared to the GIL version"},
        "memory_type": "observation",
        "confidence": 0.4,
        "source_uri": "https://outdated.example.com/nogil-benchmarks",
        "entities": ["free-threading", "Python GIL removal"],
    },
]

# Some correct data that should be corroborated
GOOD_SEEDS = [
    {
        "content": {"description": "The GIL (Global Interpreter Lock) prevents true multi-threaded parallelism in CPython"},
        "memory_type": "context",
        "confidence": 0.9,
        "source_uri": "https://docs.python.org/3/glossary.html#term-global-interpreter-lock",
        "entities": ["GIL", "CPython", "Python GIL removal"],
    },
]


def _seed_tome(store: GraphStore, seeds: list[dict], project: str) -> list[str]:
    """Seed a tome with pre-built memories. Returns memory IDs."""
    ids = []
    for seed in seeds:
        mem = make_memory(
            content=seed["content"],
            memory_type=seed["memory_type"],
            project=project,
            confidence=seed["confidence"],
        )
        mid = store.add_memory(mem)
        ids.append(mid)

        # Add source
        src = make_source(uri=seed["source_uri"], source_type="url")
        sid = store.get_or_create_source(src)
        store.link_memory_to_source(mid, sid)

        # Add entities
        for ent_name in seed.get("entities", []):
            ent = make_entity(name=ent_name, entity_type="system")
            eid = store.get_or_create_entity(ent)
            store.link_memory_to_entity(mid, eid, "about")

    return ids


class TestInvestigate:
    """Test Phoebe's autonomous investigation with seeded bad data."""

    @pytest.fixture
    def setup(self, tmp_path):
        """Create tome, seed with bad + good data, return everything."""
        tome = Tome(tmp_path / "gil-test.tome")
        tome.open()
        store = GraphStore(tome.connection())
        reasoner = Reasoner(tome.connection())

        project = "python-gil-research"
        bad_ids = _seed_tome(store, BAD_SEEDS, project)
        good_ids = _seed_tome(store, GOOD_SEEDS, project)

        return {
            "tome": tome,
            "store": store,
            "reasoner": reasoner,
            "project": project,
            "bad_ids": bad_ids,
            "good_ids": good_ids,
        }

    def test_seeded_data_exists(self, setup):
        """Verify bad data is in the tome before investigation."""
        store = setup["store"]
        project = setup["project"]

        memories = store.query_memories(project=project)
        assert len(memories) == 5  # 4 bad + 1 good

        # Verify the bad claim is there
        for mem in memories:
            content = json.loads(mem["content"]) if isinstance(mem["content"], str) else mem["content"]
            if "rejected" in content.get("description", ""):
                assert True
                return
        pytest.fail("Bad seed data not found in tome")

    def test_investigate_with_mock_sources(self, setup):
        """Test investigation with mock search/fetch that returns correct data."""
        store = setup["store"]
        reasoner = setup["reasoner"]
        project = setup["project"]
        bad_ids = setup["bad_ids"]

        # Mock search that returns "real" URLs
        def mock_search(query):
            return [
                {"url": "https://peps.python.org/pep-0703/", "title": "PEP 703", "snippet": "Making the GIL Optional"},
                {"url": "https://discuss.python.org/t/pep-703/30474", "title": "SC Notice about PEP 703", "snippet": "Steering Council accepts PEP 703"},
            ]

        # Mock fetch that returns correct information (simulating Claude extraction)
        def mock_fetch(url, prompt):
            if "pep-0703" in url:
                return json.dumps({
                    "claims": [
                        {
                            "claim": "PEP 703 was authored by Sam Gross, not Guido van Rossum",
                            "type": "context",
                            "entities": ["Sam Gross", "PEP 703", "Python GIL removal"],
                            "confidence": 0.95,
                        },
                        {
                            "claim": "PEP 703 uses biased reference counting, not tracing garbage collection, to manage memory without the GIL",
                            "type": "context",
                            "entities": ["PEP 703", "biased reference counting", "Python GIL removal"],
                            "confidence": 0.95,
                        },
                        {
                            "claim": "The free-threaded build has approximately 5-10% single-threaded performance overhead",
                            "type": "observation",
                            "entities": ["free-threading", "Python GIL removal", "CPython"],
                            "confidence": 0.9,
                        },
                        {
                            "claim": "PEP 703 makes the GIL optional via a build flag, not removed entirely",
                            "type": "decision",
                            "entities": ["PEP 703", "GIL", "Python GIL removal"],
                            "confidence": 0.95,
                        },
                    ],
                    "corrections": [
                        {
                            "existing_id": bad_ids[1],  # Guido proposed it
                            "relationship": "contradicts",
                            "reason": "PEP 703 was authored by Sam Gross, not Guido van Rossum",
                        },
                        {
                            "existing_id": bad_ids[2],  # tracing GC
                            "relationship": "contradicts",
                            "reason": "PEP 703 uses biased reference counting, not tracing garbage collection",
                        },
                        {
                            "existing_id": setup["good_ids"][0],  # GIL prevents parallelism
                            "relationship": "corroborates",
                            "reason": "PEP 703 confirms the GIL prevents true multi-threaded parallelism",
                        },
                    ],
                })
            elif "discuss.python.org" in url:
                return json.dumps({
                    "claims": [
                        {
                            "claim": "The Python Steering Council accepted PEP 703 in October 2023 with conditions",
                            "type": "decision",
                            "entities": ["Python Steering Council", "PEP 703", "Python GIL removal"],
                            "confidence": 0.95,
                        },
                        {
                            "claim": "The Steering Council set a phased approach: experimental in 3.13, supported in future release",
                            "type": "decision",
                            "entities": ["Python Steering Council", "CPython 3.13", "Python GIL removal"],
                            "confidence": 0.9,
                        },
                    ],
                    "corrections": [
                        {
                            "existing_id": bad_ids[0],  # PEP 703 was rejected
                            "relationship": "contradicts",
                            "reason": "PEP 703 was ACCEPTED by the Steering Council, not rejected",
                        },
                        {
                            "existing_id": bad_ids[3],  # zero overhead
                            "relationship": "contradicts",
                            "reason": "Free-threaded Python has measurable performance overhead, not zero",
                        },
                    ],
                })
            return json.dumps({"claims": [], "corrections": []})

        # Run investigation
        result = investigate(
            topic="Python GIL removal",
            store=store,
            reasoner=reasoner,
            search_fn=mock_search,
            fetch_fn=mock_fetch,
            project=project,
            depth="standard",
        )

        # ── Assertions ─────────────────────────────────────────────
        print("\n=== Investigation Results ===")
        print(json.dumps(result, indent=2, default=str))

        # She found and added new memories
        assert result["memories_added"] >= 4, f"Expected >=4 new memories, got {result['memories_added']}"

        # She found contradictions with bad data
        assert result["contradictions_found"] >= 2, f"Expected >=2 contradictions, got {result['contradictions_found']}"

        # She found corroborations with good data
        assert result["corroborations_found"] >= 1, f"Expected >=1 corroboration, got {result['corroborations_found']}"

        # She superseded bad memories
        assert result["memories_superseded"] >= 2, f"Expected >=2 superseded, got {result['memories_superseded']}"

        # ── Verify tome state ──────────────────────────────────────

        # Bad memories should be superseded, NOT deleted
        for bad_id in bad_ids:
            mem = store.get_memory(bad_id)
            assert mem is not None, f"Bad memory {bad_id} was DELETED — should be superseded, never deleted"

        # At least some bad memories should have status = superseded
        superseded_count = 0
        for bad_id in bad_ids:
            mem = store.get_memory(bad_id)
            if mem["status"] == "superseded":
                superseded_count += 1
        assert superseded_count >= 2, f"Expected >=2 superseded bad memories, got {superseded_count}"

        # Good memory should still be there and not superseded
        good_mem = store.get_memory(setup["good_ids"][0])
        assert good_mem is not None
        assert good_mem["status"] != "superseded", "Good memory was incorrectly superseded"

        # New entities should exist
        sam = store.find_entity_by_name("Sam Gross")
        assert sam is not None, "Sam Gross entity not created"

        # Total memories should be original + new (nothing deleted)
        all_memories = store.query_memories(project=project, limit=100)
        assert len(all_memories) >= 5 + result["memories_added"], \
            f"Memories were deleted! Expected >= {5 + result['memories_added']}, got {len(all_memories)}"

        print("\n=== Tome Final State ===")
        print(f"Total memories: {len(all_memories)}")
        print(f"Superseded: {superseded_count}")
        print(f"New entities: {result['entities_added']}")
        print(f"Contradictions: {result['contradictions_found']}")
        print(f"Corroborations: {result['corroborations_found']}")

    def test_context_brief_after_investigation(self, setup):
        """After investigation, the context brief should reflect corrected knowledge."""
        store = setup["store"]
        reasoner = setup["reasoner"]
        project = setup["project"]
        bad_ids = setup["bad_ids"]

        # Run mock investigation first
        def mock_search(q):
            return [{"url": "https://peps.python.org/pep-0703/", "title": "PEP 703"}]

        def mock_fetch(url, prompt):
            return json.dumps({
                "claims": [
                    {
                        "claim": "PEP 703 was accepted by the Steering Council",
                        "type": "decision",
                        "entities": ["PEP 703", "Python Steering Council", "Python GIL removal"],
                        "confidence": 0.95,
                    },
                ],
                "corrections": [
                    {
                        "existing_id": bad_ids[0],
                        "relationship": "contradicts",
                        "reason": "PEP 703 was accepted, not rejected",
                    },
                ],
            })

        investigate(
            topic="Python GIL removal",
            store=store,
            reasoner=reasoner,
            search_fn=mock_search,
            fetch_fn=mock_fetch,
            project=project,
        )

        # Now get the context brief
        brief = reasoner.context_brief(project, topic="Python GIL removal")

        print("\n=== Context Brief After Investigation ===")
        print(json.dumps(brief, indent=2, default=str))

        # Brief should exist and have content
        assert brief["project"] == project
        assert len(brief["recent_decisions"]) >= 1
