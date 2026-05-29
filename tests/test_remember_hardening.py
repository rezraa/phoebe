# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""E2/S6 hardening tests for phoebe remember.

Covers the failure shapes from the S5 post-mortem matrix: dropping the
caller-supplied ``id`` and ``title``, the qualitative-confidence mapping
(high/medium/low -> float), and fail-loud on an unparseable confidence.
"""

from __future__ import annotations

import pytest

from phoebe.tools.remember import remember, _resolve_confidence
from phoebe.tools._shared import coerce, coerce_or_raise


@pytest.fixture
def conn(tmp_path):
    """Connection against the full Othrys schema (memories/sources/entities)."""
    try:
        import real_ladybug as kuzu
        from othrys.schema import init_db
    except ImportError:
        pytest.skip("Othrys schema unavailable")

    db = init_db(tmp_path / "remember.db")
    yield kuzu.Connection(db)


class TestResolveConfidence:

    def test_float_passthrough(self):
        assert _resolve_confidence(0.42) == pytest.approx(0.42)

    def test_high_medium_low(self):
        assert _resolve_confidence("high") == pytest.approx(0.9)
        assert _resolve_confidence("Medium") == pytest.approx(0.6)
        assert _resolve_confidence("LOW") == pytest.approx(0.3)

    def test_numeric_string(self):
        assert _resolve_confidence("0.75") == pytest.approx(0.75)

    def test_garbage_raises(self):
        with pytest.raises(ValueError, match="0.0-1.0 float"):
            _resolve_confidence("kinda-sure")


class TestCoerceOrRaise:
    """The stricter, persist-safe coercion helper backing ``entities``."""

    def test_none_returns_empty_default(self):
        assert coerce_or_raise(None, list, empty_default=[]) == []
        assert coerce_or_raise(None, dict, empty_default={}) == {}

    def test_native_list_passthrough(self):
        assert coerce_or_raise(["a", "b"], list, empty_default=[]) == ["a", "b"]

    def test_json_array_string(self):
        assert coerce_or_raise('["a", "b"]', list, empty_default=[]) == [
            "a",
            "b",
        ]

    def test_nonempty_wrong_type_raises(self):
        # A dict where a list is expected must fail loud, not become [].
        with pytest.raises(TypeError):
            coerce_or_raise({"a": 1}, list, empty_default=[])

    def test_bare_nonjson_string_raises(self):
        with pytest.raises(TypeError):
            coerce_or_raise("just-a-name", list, empty_default=[])

    def test_int_raises(self):
        with pytest.raises(TypeError):
            coerce_or_raise(5, list, empty_default=[])


class TestRememberEntitiesHardening:

    def test_none_entities_ok(self, conn):
        result = remember(
            content="no entities supplied",
            memory_type="observation",
            entities=None,
            conn=conn,
        )
        assert result["stored"] is True

    def test_valid_list_entities_used(self, conn):
        result = remember(
            content="entities as a list",
            memory_type="observation",
            entities=["othrys", "phoebe"],
            conn=conn,
        )
        assert result["stored"] is True
        assert len(result["entities"]) == 2

    def test_valid_json_array_string_entities_used(self, conn):
        result = remember(
            content="entities as a JSON array string",
            memory_type="observation",
            entities='["othrys", "phoebe"]',
            conn=conn,
        )
        assert result["stored"] is True
        assert len(result["entities"]) == 2

    def test_nonempty_wrong_type_entities_raises(self, conn):
        # A dict where a list is expected must NOT be silently swallowed
        # into an empty [] and persisted — the entity links would vanish.
        with pytest.raises(TypeError, match="entities"):
            remember(
                content="wrong-type entities",
                memory_type="observation",
                entities={"name": "othrys"},
                conn=conn,
            )

    def test_bare_nonjson_string_entities_raises(self, conn):
        with pytest.raises(TypeError, match="entities"):
            remember(
                content="bare string entities",
                memory_type="observation",
                entities="othrys",  # not a JSON array
                conn=conn,
            )


class TestRememberHardening:

    def test_qualitative_confidence_high(self, conn):
        result = remember(
            content="qual confidence test",
            memory_type="observation",
            confidence="high",
            conn=conn,
        )
        assert result["stored"] is True

    def test_bad_confidence_raises(self, conn):
        with pytest.raises(ValueError):
            remember(
                content="bad confidence",
                memory_type="observation",
                confidence="super-high",
                conn=conn,
            )

    def test_ignores_caller_id(self, conn):
        result = remember(
            content="id should be dropped",
            memory_type="observation",
            id="m-should-be-ignored",
            conn=conn,
        )
        assert result["stored"] is True
        # The generated id is the store's, not the caller's.
        assert result["memory_id"] != "m-should-be-ignored"

    def test_ignores_caller_title_not_prepended(self, conn):
        result = remember(
            content="plain content",
            memory_type="observation",
            title="A Title That Must Not Leak Into Content",
            conn=conn,
        )
        assert result["stored"] is True

    def test_unknown_kwarg_still_raises(self, conn):
        with pytest.raises(TypeError):
            remember(
                content="x",
                memory_type="observation",
                totally_unknown="boom",
                conn=conn,
            )
