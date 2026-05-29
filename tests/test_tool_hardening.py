# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Hardening tests for phoebe's execution-pipeline coercion.

Two distinct contracts are exercised:

* ``coerce_or_raise`` for PERSISTED container fields (create_plan.epics,
  add_epic.stories, add_story.depends_on_ids) — a non-empty wrong-type value
  must fail loud rather than be silently swallowed into ``[]`` and stored.
* ``coerce_str_or_container`` for the polymorphic ``Union[dict, str, None]``
  fields (update_story.output/input_context, update_epic.output) — a plain
  string must be PRESERVED, a JSON-dict-string decoded, a dict kept, None
  passed through. These must never null a real string (the S7 trap).
"""

from __future__ import annotations

import json

import pytest

from phoebe.store import GraphStore
from phoebe.models import make_plan, make_epic, make_story
from phoebe.tools._shared import coerce_or_raise, coerce_str_or_container
from phoebe.tools.add_story import add_story
from phoebe.tools.add_epic import add_epic
from phoebe.tools.create_plan import create_plan
from phoebe.tools.update_story import update_story
from phoebe.tools.update_epic import update_epic


@pytest.fixture
def conn(tmp_path):
    """Kuzu connection against the full Othrys schema (plans/epics/stories)."""
    try:
        import real_ladybug as kuzu
        from othrys.schema import init_db
    except ImportError:
        pytest.skip("Othrys schema (plans/epics/stories) unavailable")

    db = init_db(tmp_path / "hardening.db")
    yield kuzu.Connection(db)


@pytest.fixture
def store(conn):
    return GraphStore(conn)


def _seed_plan(store, plan_id: str = "plan-h") -> str:
    plan = make_plan(name="Plan", goal="g", created_by="test", id=plan_id)
    store.add_plan(plan)
    return plan_id


def _seed_epic(store, plan_id: str) -> str:
    epic = make_epic(plan_id=plan_id, name="Epic", description="e", sequence=1)
    epic_id = store.add_epic(epic)
    store.link_plan_to_epic(plan_id, epic_id, 1)
    return epic_id


def _seed_story(store, epic_id: str) -> str:
    story = make_story(
        epic_id=epic_id,
        name="Story",
        description="s",
        phase="implementation",
        assigned_titan="mnemos",
        sequence=1,
    )
    story_id = store.add_story(story)
    store.link_epic_to_story(epic_id, story_id, 1)
    return story_id


# ---------------------------------------------------------------------------
# coerce_or_raise — persisted container fields
# ---------------------------------------------------------------------------

class TestCoerceOrRaise:

    def test_none_returns_empty_default(self):
        assert coerce_or_raise(None, list, []) == []

    def test_native_list_passthrough(self):
        assert coerce_or_raise(["a"], list, []) == ["a"]

    def test_json_array_string(self):
        assert coerce_or_raise('["a", "b"]', list, []) == ["a", "b"]

    def test_nonempty_wrong_type_raises(self):
        with pytest.raises(TypeError):
            coerce_or_raise({"a": 1}, list, [])

    def test_bare_nonjson_string_raises(self):
        with pytest.raises(TypeError):
            coerce_or_raise("solo", list, [])


class TestCreatePlanEpicsHardening:

    def test_valid_epics_list(self, conn):
        result = create_plan(
            name="P", goal="g",
            epics=[{"name": "E1", "sequence": 1, "stories": []}],
            conn=conn,
        )
        assert result["created"] is True
        assert len(result["epic_ids"]) == 1

    def test_json_string_epics(self, conn):
        result = create_plan(
            name="P", goal="g",
            epics='[{"name": "E1", "sequence": 1}]',
            conn=conn,
        )
        assert result["created"] is True
        assert len(result["epic_ids"]) == 1

    def test_nonempty_wrong_type_epics_raises(self, conn):
        # epics is REQUIRED; a dict must not be swallowed into [] and persist
        # a plan with zero epics.
        with pytest.raises(TypeError):
            create_plan(name="P", goal="g", epics={"name": "E1"}, conn=conn)


class TestAddEpicStoriesHardening:

    def test_none_stories_ok(self, store, conn):
        plan_id = _seed_plan(store)
        result = add_epic(
            plan_id=plan_id, name="E", description="d", sequence=2,
            stories=None, conn=conn,
        )
        assert result["added"] is True

    def test_nonempty_wrong_type_stories_raises(self, store, conn):
        plan_id = _seed_plan(store)
        with pytest.raises(TypeError):
            add_epic(
                plan_id=plan_id, name="E", description="d", sequence=2,
                stories={"name": "S1"}, conn=conn,
            )


class TestAddStoryDependsOnHardening:

    def test_none_depends_on_ok(self, store, conn):
        plan_id = _seed_plan(store)
        epic_id = _seed_epic(store, plan_id)
        result = add_story(
            epic_id=epic_id, name="S", description="d", phase="implementation",
            assigned_titan="mnemos", sequence=2, depends_on_ids=None, conn=conn,
        )
        assert result["added"] is True

    def test_nonempty_wrong_type_depends_on_raises(self, store, conn):
        plan_id = _seed_plan(store)
        epic_id = _seed_epic(store, plan_id)
        with pytest.raises(TypeError):
            add_story(
                epic_id=epic_id, name="S", description="d",
                phase="implementation", assigned_titan="mnemos", sequence=2,
                depends_on_ids={"id": "x"}, conn=conn,
            )


# ---------------------------------------------------------------------------
# coerce_str_or_container — polymorphic Union[dict, str, None] (the S7 trap)
# ---------------------------------------------------------------------------

class TestCoerceStrOrContainer:

    def test_none_passthrough(self):
        assert coerce_str_or_container(None, dict) is None

    def test_dict_kept(self):
        assert coerce_str_or_container({"a": 1}, dict) == {"a": 1}

    def test_json_dict_string_decoded(self):
        assert coerce_str_or_container('{"a": 1}', dict) == {"a": 1}

    def test_plain_string_preserved(self):
        # The S7 trap: a real string must NOT be nulled.
        assert coerce_str_or_container("just a note", dict) == "just a note"

    def test_json_nondict_string_preserved_as_string(self):
        # "[1,2]" parses to a list, not the expected dict -> keep the string.
        assert coerce_str_or_container("[1, 2]", dict) == "[1, 2]"


class TestUpdateStoryPolymorphicOutput:

    def test_dict_output_persisted_as_json(self, store, conn):
        plan_id = _seed_plan(store)
        epic_id = _seed_epic(store, plan_id)
        story_id = _seed_story(store, epic_id)

        update_story(story_id, output={"k": "v"}, conn=conn)
        story = store.get_story(story_id)
        assert story["output"] == "JSON:" + json.dumps({"k": "v"})

    def test_json_string_output_decoded_then_persisted(self, store, conn):
        plan_id = _seed_plan(store)
        epic_id = _seed_epic(store, plan_id)
        story_id = _seed_story(store, epic_id)

        update_story(story_id, output='{"k": "v"}', conn=conn)
        story = store.get_story(story_id)
        assert story["output"] == "JSON:" + json.dumps({"k": "v"})

    def test_plain_string_output_preserved(self, store, conn):
        plan_id = _seed_plan(store)
        epic_id = _seed_epic(store, plan_id)
        story_id = _seed_story(store, epic_id)

        update_story(story_id, output="a plain status note", conn=conn)
        story = store.get_story(story_id)
        # Preserved verbatim, NOT nulled and NOT JSON-wrapped.
        assert story["output"] == "a plain status note"

    def test_plain_string_input_context_preserved(self, store, conn):
        plan_id = _seed_plan(store)
        epic_id = _seed_epic(store, plan_id)
        story_id = _seed_story(store, epic_id)

        result = update_story(
            story_id, input_context="raw context blob", conn=conn,
        )
        assert "input_context" in result["fields_updated"]
        story = store.get_story(story_id)
        assert story["input_context"] == "raw context blob"

    def test_none_output_not_updated(self, store, conn):
        plan_id = _seed_plan(store)
        epic_id = _seed_epic(store, plan_id)
        story_id = _seed_story(store, epic_id)

        result = update_story(story_id, status="in_progress", conn=conn)
        assert "output" not in result["fields_updated"]


class TestUpdateEpicPolymorphicOutput:

    def test_plain_string_output_preserved(self, store, conn):
        plan_id = _seed_plan(store)
        epic_id = _seed_epic(store, plan_id)

        update_epic(epic_id, output="epic summary text", conn=conn)
        rows = store._execute(
            "MATCH (e:epics) WHERE e.id = $id RETURN e.data", {"id": epic_id},
        )
        parsed = json.loads(rows[0][0][5:])
        assert parsed["output"] == "epic summary text"

    def test_json_dict_string_output_decoded(self, store, conn):
        plan_id = _seed_plan(store)
        epic_id = _seed_epic(store, plan_id)

        update_epic(epic_id, output='{"done": true}', conn=conn)
        rows = store._execute(
            "MATCH (e:epics) WHERE e.id = $id RETURN e.data", {"id": epic_id},
        )
        parsed = json.loads(rows[0][0][5:])
        assert parsed["output"] == {"done": True}

    def test_none_output_not_updated(self, store, conn):
        plan_id = _seed_plan(store)
        epic_id = _seed_epic(store, plan_id)

        result = update_epic(epic_id, status="in_progress", conn=conn)
        assert "output" not in result["fields_updated"]
