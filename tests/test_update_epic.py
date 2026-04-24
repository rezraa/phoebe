# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Tests for update_epic — mirrors the shape of update_story."""

from __future__ import annotations

import json

import pytest

from phoebe.store import GraphStore
from phoebe.models import make_plan, make_epic
from phoebe.tools.update_epic import update_epic


@pytest.fixture
def conn(tmp_path):
    """Kuzu connection against the full Othrys schema (plans/epics/stories).

    The plan/epic/story tables live in Othrys's schema, not Phoebe's
    standalone tome, so tests that exercise the execution-pipeline tools
    must spin up an Othrys DB.
    """
    try:
        import real_ladybug as kuzu
        from othrys.schema import init_db
    except ImportError:
        pytest.skip("Othrys schema (plans/epics/stories) unavailable")

    db = init_db(tmp_path / "update_epic.db")
    c = kuzu.Connection(db)
    yield c


@pytest.fixture
def store(conn):
    return GraphStore(conn)


# Back-compat alias for tests that used the old ``tome`` fixture name.
@pytest.fixture
def tome(conn):
    class _Shim:
        def __init__(self, c):
            self._c = c

        def connection(self):
            return self._c

    return _Shim(conn)


def _seed_epic(store, plan_id: str = "plan-1") -> str:
    """Create a plan + epic, return the epic id."""
    plan = make_plan(
        name="Test plan",
        goal="t",
        created_by="test",
        id=plan_id,
    )
    store.add_plan(plan)
    epic = make_epic(
        plan_id=plan_id,
        name="Test epic",
        description="e",
        sequence=1,
    )
    epic_id = store.add_epic(epic)
    store.link_plan_to_epic(plan_id, epic_id, 1)
    return epic_id


def _read_epic(store, epic_id: str) -> dict:
    rows = store._execute(
        "MATCH (e:epics) WHERE e.id = $id RETURN e",
        {"id": epic_id},
    )
    return rows[0][0] if rows else {}


class TestUpdateEpic:
    def test_update_status_only(self, store, tome):
        epic_id = _seed_epic(store)

        result = update_epic(epic_id, status="in_progress", conn=tome.connection())

        assert result == {
            "updated": True,
            "epic_id": epic_id,
            "fields_updated": ["status"],
        }
        epic = _read_epic(store, epic_id)
        assert epic["status"] == "in_progress"

    def test_update_output_stored_in_data(self, store, tome):
        epic_id = _seed_epic(store)

        payload = {"summary": "shipped", "artifacts": ["a", "b"]}
        result = update_epic(epic_id, output=payload, conn=tome.connection())

        assert result["fields_updated"] == ["output"]
        epic = _read_epic(store, epic_id)
        raw = epic["data"]
        assert isinstance(raw, str) and raw.startswith("JSON:")
        parsed = json.loads(raw[5:])
        assert parsed["output"] == payload
        # Status untouched.
        assert epic["status"] == "planned"

    def test_update_status_and_output_together(self, store, tome):
        epic_id = _seed_epic(store)

        result = update_epic(
            epic_id,
            status="completed",
            output={"done": True},
            conn=tome.connection(),
        )

        assert set(result["fields_updated"]) == {"status", "output"}
        epic = _read_epic(store, epic_id)
        assert epic["status"] == "completed"
        parsed = json.loads(epic["data"][5:])
        assert parsed["output"] == {"done": True}

    def test_output_merges_with_existing_data(self, store, tome):
        epic_id = _seed_epic(store)
        # Pre-seed data with an unrelated key.
        store.update_epic(
            epic_id,
            data="JSON:" + json.dumps({"notes": "keep me"}),
        )

        update_epic(epic_id, output={"r": 1}, conn=tome.connection())

        epic = _read_epic(store, epic_id)
        parsed = json.loads(epic["data"][5:])
        assert parsed["notes"] == "keep me"
        assert parsed["output"] == {"r": 1}

    def test_output_accepts_json_string(self, store, tome):
        epic_id = _seed_epic(store)

        result = update_epic(
            epic_id,
            output=json.dumps({"from": "string"}),
            conn=tome.connection(),
        )

        assert result["fields_updated"] == ["output"]
        epic = _read_epic(store, epic_id)
        parsed = json.loads(epic["data"][5:])
        assert parsed["output"] == {"from": "string"}

    def test_no_fields_no_writes(self, store, tome):
        epic_id = _seed_epic(store)
        before = _read_epic(store, epic_id)

        result = update_epic(epic_id, conn=tome.connection())

        assert result == {
            "updated": True,
            "epic_id": epic_id,
            "fields_updated": [],
        }
        after = _read_epic(store, epic_id)
        assert after["status"] == before["status"]
        assert after["data"] == before["data"]

    def test_exported_from_tools_package(self):
        from phoebe.tools import update_epic as exported
        assert exported is update_epic
