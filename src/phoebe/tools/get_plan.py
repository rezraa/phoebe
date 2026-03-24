# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Read the full plan tree — plan, epics, stories, statuses."""

from __future__ import annotations

from typing import Any

from phoebe.tools._shared import get_store


def _find_plan_by_name(store: Any, name: str) -> dict | None:
    """Find a plan by case-insensitive substring match on name."""
    needle = name.lower()
    # Use the store's connection to search all plans
    rows = store._execute(
        "MATCH (p:plans) RETURN p ORDER BY p.created_at DESC"
    )
    for row in rows:
        plan = row[0]
        plan_name = (plan.get("name") or "").lower()
        if needle in plan_name:
            return plan
    return None


def get_plan(
    plan_id: str | None = None,
    name: str | None = None,
    conn: Any = None,
) -> dict:
    """Read a full execution plan with all epics and stories.

    Lookup order:
    1. If plan_id is given, fetch by exact ID.
    2. If name is given, search by case-insensitive substring match.
    3. Otherwise, return the most recently created plan.

    Args:
        plan_id: ID of the plan to read (e.g. "plan-8f45bad9").
        name: Search by plan name (case-insensitive substring match,
              e.g. "File Viewer" matches "File Viewer" plan).
        conn: Kuzu connection (Othrys mode) or None (standalone).

    Returns:
        {
            plan: {id, name, goal, status, created_at, ...},
            epics: [
                {
                    id, name, sequence, status, ...,
                    stories: [
                        {id, name, phase, assigned_titan, status,
                         sequence, input_context, output, ...}
                    ]
                }
            ],
            summary: {
                total_stories, pending, in_progress, completed,
                blocked, failed
            }
        }
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

    for epic in epics_raw:
        stories = store.get_stories_for_epic(epic["id"])
        for s in stories:
            summary["total_stories"] += 1
            st = s.get("status", "pending")
            if st in summary:
                summary[st] += 1

        epics_out.append({
            **epic,
            "stories": stories,
        })

    return {
        "plan": plan,
        "epics": epics_out,
        "summary": summary,
    }
