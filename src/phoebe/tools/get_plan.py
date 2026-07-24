# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Read the full plan tree — plan, epics, stories, statuses."""

from __future__ import annotations

from typing import Any

from phoebe.store import _PLAN_SKELETON_COLS
from phoebe.tools._shared import get_store


def _find_plan_by_name(store: Any, name: str) -> dict | None:
    """Find a plan by case-insensitive substring match on name.

    Skeleton-column projection (no ``RETURN p`` -> no driver ``_ID``/``_LABEL``
    pointers, no heavy ``data`` blob), same shape as ``store.get_plan``.
    """
    needle = name.lower()
    plans = store._project(
        match="MATCH (p:plans)",
        alias="p",
        cols=_PLAN_SKELETON_COLS,
        params={},
        order=" ORDER BY p.created_at DESC",
    )
    for plan in plans:
        plan_name = (plan.get("name") or "").lower()
        if needle in plan_name:
            return plan
    return None


def get_plan(
    plan_id: str | None = None,
    name: str | None = None,
    epic_id: str | None = None,
    conn: Any = None,
) -> dict:
    """Read an execution plan's epics and stories (name-only story navigation).

    Lookup order:
    1. If plan_id is given, fetch by exact ID.
    2. If name is given, search by case-insensitive substring match.
    3. Otherwise, return the most recently created plan.

    Args:
        plan_id: ID of the plan to read (e.g. "plan-8f45bad9").
        name: Search by plan name (case-insensitive substring match,
              e.g. "File Viewer" matches "File Viewer" plan).
        epic_id: Optional escape hatch for big plans. When given, the returned
              ``epics`` list holds ONLY that one epic's subtree (its lean
              stories) — but ``summary`` STILL counts every story in the whole
              plan, never just the scoped epic. Omit for the full tree.
        conn: Kuzu connection (Othrys mode) or None (standalone).

    Returns (LEAN tree — no per-story description / AC / transcripts):
        {
            plan: {id, name, goal, status, created_at, ...},
            epics: [
                {
                    id, name, description, sequence, status,
                    acceptance_criteria,
                    stories: [
                        {id, name, phase, assigned_titan, sequence, status}
                    ]
                }
            ],
            summary: {
                total_stories, pending, in_progress, completed,
                blocked, failed
            }
        }

    EPICS keep their ``description`` + ``acceptance_criteria`` (coarse
    wayfinding). STORIES are name-only here — a story's ``description``,
    ``acceptance_criteria``, ``input_context``, ``output`` (and
    ``full_output``) are NOT in this tree. Drill down for them via the
    ``get_stories`` tool with the ids you need.
    """
    store = get_store(conn)

    # Find the plan
    if plan_id:
        plan = store.get_plan(plan_id)
    elif name:
        plan = _find_plan_by_name(store, name)
    else:
        plan = store.get_latest_plan()

    if not plan:
        return {"error": "No plan found", "plan": None, "epics": []}

    pid = plan["id"]

    # Get epics with their stories
    epics_raw = store.get_epics_for_plan(pid)
    epics_out = []
    summary = {
        "total_stories": 0,
        "pending": 0,
        "in_progress": 0,
        "completed": 0,
        "blocked": 0,
        "failed": 0,
    }

    # Iterate EVERY epic so ``summary`` is a GLOBAL plan roll-up. When
    # ``epic_id`` scopes the read, only the matching epic's subtree is emitted
    # into ``epics``, but the counts above still cover the whole plan — a scoped
    # summary that under-reports totals is the lie the brief D6 gate outlawed.
    for epic in epics_raw:
        stories = store.get_stories_for_epic(epic["id"])
        for s in stories:
            summary["total_stories"] += 1
            st = s.get("status", "pending")
            if st in summary:
                summary[st] += 1

        if epic_id is None or epic["id"] == epic_id:
            epics_out.append({
                **epic,
                "stories": stories,
            })

    return {
        "plan": plan,
        "epics": epics_out,
        "summary": summary,
    }
