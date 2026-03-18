#!/usr/bin/env python3
# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""A/B Test: Python GIL Removal — With vs Without Phoebe's Context.

Asks the same questions to Claude with and without Phoebe's tome context.
Measures: accuracy against ground truth, response time, source attribution.

Requirements:
  - Dashboard running (./start.sh) with investigated tome
  - ANTHROPIC_API_KEY env var set

Usage:
  PYTHONPATH=src .venv/bin/python3 tests/ab_test_gil.py
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

import websockets

# ---------------------------------------------------------------------------
# Ground truth + questions
# ---------------------------------------------------------------------------

QUESTIONS = [
    {
        "id": "Q1",
        "question": "Who authored PEP 703 and what does it propose?",
        "ground_truth": "Sam Gross authored PEP 703, proposing making the Global Interpreter Lock (GIL) optional in CPython via a compile-time flag.",
        "key_facts": ["Sam Gross", "optional", "compile-time flag", "not removed entirely"],
        "trap_facts": ["Guido van Rossum"],  # wrong if mentioned as author
    },
    {
        "id": "Q2",
        "question": "How does the free-threaded build handle memory management without the GIL?",
        "ground_truth": "PEP 703 uses biased reference counting and immortalization of frequently-shared objects to manage memory safely without the GIL.",
        "key_facts": ["biased reference counting", "immortalization"],
        "trap_facts": ["tracing garbage collection", "removes reference counting"],
    },
    {
        "id": "Q3",
        "question": "Was PEP 703 accepted or rejected? What conditions were set?",
        "ground_truth": "PEP 703 was accepted by the Steering Council with conditions: gradual phased rollout, ability to roll back if too disruptive.",
        "key_facts": ["accepted", "phased", "roll back", "gradual"],
        "trap_facts": ["rejected"],
    },
    {
        "id": "Q4",
        "question": "What are the three phases of the GIL removal rollout?",
        "ground_truth": "Phase I: experimental in Python 3.13. Phase II: officially supported but optional. Phase III: free-threaded becomes the default.",
        "key_facts": ["Phase I", "experimental", "3.13", "Phase II", "supported", "optional", "Phase III", "default"],
        "trap_facts": [],
    },
    {
        "id": "Q5",
        "question": "What is the performance overhead of the free-threaded build?",
        "ground_truth": "The free-threaded build has approximately 5-10% single-threaded performance overhead.",
        "key_facts": ["5", "10", "overhead", "single-threaded"],
        "trap_facts": ["zero overhead", "no overhead"],
    },
    {
        "id": "Q6",
        "question": "What is the current status of free-threaded Python as of Python 3.14?",
        "ground_truth": "As of Python 3.14 (PEP 779), free-threaded Python moved to Phase II — officially supported, no longer experimental.",
        "key_facts": ["3.14", "PEP 779", "Phase II", "no longer experimental", "officially supported"],
        "trap_facts": [],
    },
    {
        "id": "Q7",
        "question": "Where did Sam Gross develop the initial nogil prototype?",
        "ground_truth": "Sam Gross developed the nogil fork of CPython at Meta, proving that GIL removal was feasible.",
        "key_facts": ["Meta", "nogil", "fork", "feasible"],
        "trap_facts": [],
    },
]


def score_response(response: str, question: dict) -> dict:
    """Score a response against ground truth."""
    response_lower = response.lower()

    # Count key facts mentioned
    key_hits = []
    key_misses = []
    for fact in question["key_facts"]:
        if fact.lower() in response_lower:
            key_hits.append(fact)
        else:
            key_misses.append(fact)

    # Count trap facts (wrong info) mentioned
    traps_hit = []
    for trap in question["trap_facts"]:
        if trap.lower() in response_lower:
            traps_hit.append(trap)

    total_facts = len(question["key_facts"])
    accuracy = len(key_hits) / total_facts if total_facts > 0 else 1.0
    has_wrong_info = len(traps_hit) > 0

    return {
        "accuracy": accuracy,
        "key_hits": key_hits,
        "key_misses": key_misses,
        "traps_hit": traps_hit,
        "has_wrong_info": has_wrong_info,
        "total_key_facts": total_facts,
    }


async def get_tome_context(ws_url: str = "ws://127.0.0.1:8888/ws") -> str:
    """Query the tome via WebSocket and build a context string."""
    async with websockets.connect(ws_url) as ws:
        # Skip initial graph broadcast
        await ws.recv()

        # Query all memories
        await ws.send(json.dumps({"cmd": "query", "project": "python-gil", "limit": 50}))
        while True:
            raw = await ws.recv()
            resp = json.loads(raw)
            if "memories" in resp:
                break

        memories = resp.get("memories", [])

        # Build context string from non-superseded memories
        context_lines = []
        for mem in memories:
            if mem.get("status") == "superseded":
                continue
            try:
                content = json.loads(mem["content"]) if isinstance(mem["content"], str) else mem["content"]
                desc = content.get("description", "")
                conf = mem.get("confidence", 0)
                mtype = mem.get("memory_type", "")
                context_lines.append(f"[{mtype}, confidence: {conf:.0%}] {desc}")
            except (json.JSONDecodeError, TypeError):
                pass

        return "\n".join(context_lines)


def ask_claude(question: str, context: str | None = None) -> tuple[str, float]:
    """Ask Claude a question, optionally with Phoebe's context. Returns (response, time_seconds)."""
    try:
        import anthropic
    except ImportError:
        print("ERROR: pip install anthropic")
        return ("", 0.0)

    client = anthropic.Anthropic()

    if context:
        prompt = (
            f"You have the following verified project knowledge from Phoebe's knowledge graph:\n\n"
            f"{context}\n\n"
            f"Based on this knowledge, answer the following question concisely:\n{question}"
        )
    else:
        prompt = f"Answer the following question concisely based on your knowledge:\n{question}"

    start = time.time()
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed = time.time() - start

    text = response.content[0].text if response.content else ""
    return text, elapsed


def run_ab_test():
    """Run the full A/B comparison."""
    print("═" * 70)
    print("  Phoebe A/B Test — Python GIL Removal")
    print("  Condition A: Claude alone (no context)")
    print("  Condition B: Claude + Phoebe's tome context")
    print("═" * 70)
    print()

    # Get tome context
    print("Fetching Phoebe's context from tome...")
    try:
        context = asyncio.run(get_tome_context())
        context_lines = context.strip().split("\n")
        print(f"  Got {len(context_lines)} active memories")
        print()
    except Exception as e:
        print(f"  ERROR connecting to dashboard: {e}")
        print("  Make sure ./start.sh is running with the investigated tome")
        return

    # Run both conditions
    results_a = []  # Without Phoebe
    results_b = []  # With Phoebe

    for q in QUESTIONS:
        print(f"─── {q['id']}: {q['question']}")
        print()

        # Condition A: No context
        print("  [A] Claude alone...")
        resp_a, time_a = ask_claude(q["question"])
        score_a = score_response(resp_a, q)
        results_a.append({"question": q, "response": resp_a, "time": time_a, "score": score_a})
        print(f"      Time: {time_a:.2f}s | Accuracy: {score_a['accuracy']:.0%} | Wrong info: {score_a['has_wrong_info']}")
        if score_a["key_misses"]:
            print(f"      Missed: {', '.join(score_a['key_misses'])}")
        if score_a["traps_hit"]:
            print(f"      ⚠ WRONG: {', '.join(score_a['traps_hit'])}")

        # Condition B: With Phoebe context
        print("  [B] Claude + Phoebe...")
        resp_b, time_b = ask_claude(q["question"], context=context)
        score_b = score_response(resp_b, q)
        results_b.append({"question": q, "response": resp_b, "time": time_b, "score": score_b})
        print(f"      Time: {time_b:.2f}s | Accuracy: {score_b['accuracy']:.0%} | Wrong info: {score_b['has_wrong_info']}")
        if score_b["key_misses"]:
            print(f"      Missed: {', '.join(score_b['key_misses'])}")
        if score_b["traps_hit"]:
            print(f"      ⚠ WRONG: {', '.join(score_b['traps_hit'])}")
        print()

    # Summary
    print("═" * 70)
    print("  RESULTS SUMMARY")
    print("═" * 70)
    print()

    avg_acc_a = sum(r["score"]["accuracy"] for r in results_a) / len(results_a)
    avg_acc_b = sum(r["score"]["accuracy"] for r in results_b) / len(results_b)
    avg_time_a = sum(r["time"] for r in results_a) / len(results_a)
    avg_time_b = sum(r["time"] for r in results_b) / len(results_b)
    wrong_a = sum(1 for r in results_a if r["score"]["has_wrong_info"])
    wrong_b = sum(1 for r in results_b if r["score"]["has_wrong_info"])
    total_hits_a = sum(len(r["score"]["key_hits"]) for r in results_a)
    total_hits_b = sum(len(r["score"]["key_hits"]) for r in results_b)
    total_facts = sum(r["score"]["total_key_facts"] for r in results_a)

    print(f"  {'Metric':<30} {'A (no Phoebe)':>15} {'B (+ Phoebe)':>15} {'Delta':>10}")
    print(f"  {'─' * 70}")
    print(f"  {'Avg accuracy':<30} {avg_acc_a:>14.1%} {avg_acc_b:>14.1%} {avg_acc_b - avg_acc_a:>+9.1%}")
    print(f"  {'Key facts found':<30} {total_hits_a:>12}/{total_facts} {total_hits_b:>12}/{total_facts} {total_hits_b - total_hits_a:>+9}")
    print(f"  {'Wrong info responses':<30} {wrong_a:>15} {wrong_b:>15} {wrong_b - wrong_a:>+9}")
    print(f"  {'Avg response time':<30} {avg_time_a:>13.2f}s {avg_time_b:>13.2f}s {avg_time_b - avg_time_a:>+8.2f}s")
    print()

    uplift = ((avg_acc_b - avg_acc_a) / avg_acc_a * 100) if avg_acc_a > 0 else 0
    print(f"  Accuracy uplift: {uplift:+.1f}%")
    print(f"  Wrong info eliminated: {wrong_a - wrong_b}")
    print()

    # Per-question breakdown
    print("  Per-question breakdown:")
    print(f"  {'Q':<4} {'A acc':>8} {'B acc':>8} {'A wrong':>8} {'B wrong':>8} {'Winner':>8}")
    for ra, rb in zip(results_a, results_b):
        qid = ra["question"]["id"]
        winner = "B" if rb["score"]["accuracy"] > ra["score"]["accuracy"] else ("A" if ra["score"]["accuracy"] > rb["score"]["accuracy"] else "tie")
        if ra["score"]["has_wrong_info"] and not rb["score"]["has_wrong_info"]:
            winner = "B"
        print(f"  {qid:<4} {ra['score']['accuracy']:>7.0%} {rb['score']['accuracy']:>7.0%} {'yes' if ra['score']['has_wrong_info'] else 'no':>8} {'yes' if rb['score']['has_wrong_info'] else 'no':>8} {winner:>8}")

    print()
    print("═" * 70)


if __name__ == "__main__":
    run_ab_test()
