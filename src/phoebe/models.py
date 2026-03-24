# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Data models for Phoebe's graph nodes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str = "m") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

MEMORY_TYPES = {
    "decision", "context", "observation", "requirement", "risk",
    "lesson", "incident", "change", "assumption", "question",
}

MEMORY_STATUSES = {"open", "resolved", "deferred", "abandoned", "superseded"}

MEMORY_OUTCOMES = {"success", "failure", "abandoned", "unknown"}


def make_memory(
    content: dict[str, Any],
    memory_type: str,
    *,
    status: str = "open",
    outcome: str | None = None,
    agent: str = "phoebe",
    project: str = "",
    confidence: float = 0.8,
    id: str | None = None,
) -> dict[str, Any]:
    """Create a memory node dict ready for insertion."""
    import json
    return {
        "id": id or _id("m"),
        "content": json.dumps(content) if isinstance(content, dict) else content,
        "memory_type": memory_type,
        "status": status,
        "outcome": outcome or "unknown",
        "agent": agent,
        "project": project,
        "confidence": confidence,
        "timestamp": _now(),
    }


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------

SOURCE_TYPES = {
    "slack", "gdrive", "confluence", "file", "url", "meeting",
    "conversation", "code", "github_pr", "github_issue", "jira", "email",
}


def make_source(
    uri: str,
    source_type: str,
    *,
    name: str = "",
    extraction_model: str = "",
    data: dict[str, Any] | None = None,
    id: str | None = None,
) -> dict[str, Any]:
    """Create a source node dict ready for insertion."""
    import json
    return {
        "id": id or _id("s"),
        "uri": uri,
        "source_type": source_type,
        "name": name or uri.split("/")[-1],
        "last_crawled": _now(),
        "last_verified": _now(),
        "stale": False,
        "extraction_model": extraction_model,
        "data": json.dumps(data) if data else "{}",
    }


# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------

ENTITY_TYPES = {
    "person", "team", "system", "service", "component", "pattern",
    "decision", "project", "tool", "library", "api", "config",
}


def make_entity(
    name: str,
    entity_type: str,
    *,
    data: dict[str, Any] | None = None,
    id: str | None = None,
) -> dict[str, Any]:
    """Create an entity node dict ready for insertion."""
    import json
    return {
        "id": id or _id("e"),
        "name": name,
        "entity_type": entity_type,
        "data": json.dumps(data) if data else "{}",
    }


# ---------------------------------------------------------------------------
# Milestone
# ---------------------------------------------------------------------------

MILESTONE_TYPES = {
    "sprint", "release", "version", "incident", "migration", "deadline",
}


def make_milestone(
    name: str,
    milestone_type: str,
    *,
    start_date: str = "",
    end_date: str = "",
    status: str = "planned",
    data: dict[str, Any] | None = None,
    id: str | None = None,
) -> dict[str, Any]:
    """Create a milestone node dict ready for insertion."""
    import json
    return {
        "id": id or _id("ms"),
        "name": name,
        "milestone_type": milestone_type,
        "start_date": start_date or _now(),
        "end_date": end_date,
        "status": status,
        "data": json.dumps(data) if data else "{}",
    }


# ---------------------------------------------------------------------------
# Execution pipeline — plans, epics, stories
# ---------------------------------------------------------------------------

PLAN_STATUSES = {"planned", "in_progress", "completed", "blocked", "cancelled"}

EPIC_STATUSES = {"planned", "in_progress", "completed", "blocked", "cancelled"}

STORY_STATUSES = {"pending", "in_progress", "completed", "blocked", "failed"}

STORY_PHASES = {
    "context", "architecture", "design", "implementation",
    "testing", "security", "review", "done",
}


def make_plan(
    name: str,
    goal: str,
    *,
    status: str = "planned",
    created_by: str = "prometheus",
    data: dict[str, Any] | None = None,
    id: str | None = None,
) -> dict[str, Any]:
    """Create a plan node dict ready for insertion."""
    import json
    now = _now()
    return {
        "id": id or _id("plan"),
        "name": name,
        "goal": goal,
        "status": status,
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
        "data": json.dumps(data) if data else "{}",
    }


def make_epic(
    plan_id: str,
    name: str,
    description: str,
    *,
    sequence: int = 1,
    status: str = "planned",
    acceptance_criteria: str = "",
    data: dict[str, Any] | None = None,
    id: str | None = None,
) -> dict[str, Any]:
    """Create an epic node dict ready for insertion."""
    import json
    return {
        "id": id or _id("epic"),
        "plan_id": plan_id,
        "name": name,
        "description": description,
        "sequence": sequence,
        "status": status,
        "acceptance_criteria": acceptance_criteria,
        "data": json.dumps(data) if data else "{}",
    }


def make_story(
    epic_id: str,
    name: str,
    description: str,
    *,
    phase: str = "implementation",
    assigned_titan: str = "",
    sequence: int = 1,
    status: str = "pending",
    input_context: dict[str, Any] | None = None,
    output: dict[str, Any] | None = None,
    acceptance_criteria: str = "",
    data: dict[str, Any] | None = None,
    id: str | None = None,
) -> dict[str, Any]:
    """Create a story node dict ready for insertion."""
    import json
    now = _now()
    return {
        "id": id or _id("story"),
        "epic_id": epic_id,
        "name": name,
        "description": description,
        "phase": phase,
        "assigned_titan": assigned_titan,
        "sequence": sequence,
        "status": status,
        "input_context": json.dumps(input_context) if input_context else "{}",
        "output": json.dumps(output) if output else "{}",
        "acceptance_criteria": acceptance_criteria,
        "created_at": now,
        "updated_at": now,
        "data": json.dumps(data) if data else "{}",
    }
