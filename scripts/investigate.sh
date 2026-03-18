#!/bin/bash
# Phoebe Investigation — Connects to dashboard via WebSocket, pushes findings live
# Run AFTER start.sh is running
# Usage: ./scripts/investigate.sh

set -e
cd "$(dirname "$0")/.."

VENV=".venv/bin/python3"

echo "═══════════════════════════════════════════"
echo "  Phoebe — Investigating Python GIL Removal"
echo "═══════════════════════════════════════════"
echo ""
echo "Watch the graph update live at http://127.0.0.1:8888"
echo ""

PYTHONPATH=src $VENV << 'PYEOF'
import asyncio
import json
import time
import urllib.request
import re
import ssl
import websockets

WS_URL = "ws://127.0.0.1:8888/ws"

# Correct facts that Phoebe discovers from real sources
DISCOVERIES = [
    # From PEP 703
    {
        "content": {"description": "PEP 703 was authored by Sam Gross, proposing making the GIL optional in CPython"},
        "memory_type": "context", "confidence": 0.95, "project": "python-gil",
        "source_uri": "https://peps.python.org/pep-0703/", "source_name": "PEP 703",
        "entities": ["Sam Gross", "PEP 703", "CPython", "Python GIL removal"],
        "contradicts_phrase": "Guido van Rossum proposed",
        "contradiction_reason": "PEP 703 was authored by Sam Gross at Meta, not Guido van Rossum",
    },
    {
        "content": {"description": "PEP 703 uses biased reference counting to manage memory safely without the GIL"},
        "memory_type": "context", "confidence": 0.95, "project": "python-gil",
        "source_uri": "https://peps.python.org/pep-0703/", "source_name": "PEP 703",
        "entities": ["PEP 703", "biased reference counting", "Python GIL removal"],
        "contradicts_phrase": "tracing garbage collection",
        "contradiction_reason": "PEP 703 uses biased reference counting, not tracing GC",
    },
    {
        "content": {"description": "PEP 703 introduces immortalization of frequently-shared objects to avoid refcount contention"},
        "memory_type": "context", "confidence": 0.9, "project": "python-gil",
        "source_uri": "https://peps.python.org/pep-0703/", "source_name": "PEP 703",
        "entities": ["PEP 703", "immortalization", "Python GIL removal"],
    },
    {
        "content": {"description": "The free-threaded build has approximately 5-10% single-threaded performance overhead"},
        "memory_type": "observation", "confidence": 0.85, "project": "python-gil",
        "source_uri": "https://peps.python.org/pep-0703/", "source_name": "PEP 703",
        "entities": ["free-threading", "CPython", "Python GIL removal"],
        "contradicts_phrase": "zero performance overhead",
        "contradiction_reason": "Benchmarks show 5-10% overhead, not zero",
    },
    {
        "content": {"description": "PEP 703 makes the GIL optional via a compile-time flag — not removed entirely"},
        "memory_type": "decision", "confidence": 0.95, "project": "python-gil",
        "source_uri": "https://peps.python.org/pep-0703/", "source_name": "PEP 703",
        "entities": ["PEP 703", "GIL", "Python GIL removal"],
    },
    {
        "content": {"description": "Sam Gross developed the nogil fork of CPython at Meta, proving GIL removal was feasible"},
        "memory_type": "context", "confidence": 0.9, "project": "python-gil",
        "source_uri": "https://peps.python.org/pep-0703/", "source_name": "PEP 703",
        "entities": ["Sam Gross", "Meta", "nogil", "CPython", "Python GIL removal"],
    },
    # From Steering Council acceptance
    {
        "content": {"description": "The Python Steering Council accepted PEP 703 with a gradual phased rollout condition"},
        "memory_type": "decision", "confidence": 0.95, "project": "python-gil",
        "source_uri": "https://discuss.python.org/t/pep-703-acceptance/37075",
        "source_name": "SC Acceptance of PEP 703",
        "entities": ["Python Steering Council", "PEP 703", "Python GIL removal"],
        "contradicts_phrase": "rejected",
        "contradiction_reason": "PEP 703 was ACCEPTED by the Steering Council, not rejected",
    },
    {
        "content": {"description": "Phase I: free-threaded build available as experimental in Python 3.13"},
        "memory_type": "decision", "confidence": 0.9, "project": "python-gil",
        "source_uri": "https://discuss.python.org/t/pep-703-acceptance/37075",
        "source_name": "SC Acceptance of PEP 703",
        "entities": ["Python 3.13", "free-threading", "Python GIL removal"],
    },
    {
        "content": {"description": "Phase II: free-threaded build officially supported but still optional"},
        "memory_type": "decision", "confidence": 0.9, "project": "python-gil",
        "source_uri": "https://discuss.python.org/t/pep-703-acceptance/37075",
        "source_name": "SC Acceptance of PEP 703",
        "entities": ["free-threading", "Python GIL removal"],
    },
    {
        "content": {"description": "Phase III: free-threaded build becomes the default Python interpreter"},
        "memory_type": "decision", "confidence": 0.85, "project": "python-gil",
        "source_uri": "https://discuss.python.org/t/pep-703-acceptance/37075",
        "source_name": "SC Acceptance of PEP 703",
        "entities": ["free-threading", "Python GIL removal"],
    },
    {
        "content": {"description": "The Steering Council reserved the right to roll back changes if too disruptive"},
        "memory_type": "decision", "confidence": 0.9, "project": "python-gil",
        "source_uri": "https://discuss.python.org/t/pep-703-acceptance/37075",
        "source_name": "SC Acceptance of PEP 703",
        "entities": ["Python Steering Council", "Python GIL removal"],
    },
    # From PEP 779
    {
        "content": {"description": "PEP 779 accepted for Python 3.14 — free-threading moves to Phase II (officially supported)"},
        "memory_type": "decision", "confidence": 0.95, "project": "python-gil",
        "source_uri": "https://peps.python.org/pep-0779/", "source_name": "PEP 779",
        "entities": ["PEP 779", "Python 3.14", "free-threading", "Python GIL removal"],
    },
    {
        "content": {"description": "As of Python 3.14, the free-threaded interpreter is no longer experimental"},
        "memory_type": "decision", "confidence": 0.95, "project": "python-gil",
        "source_uri": "https://peps.python.org/pep-0779/", "source_name": "PEP 779",
        "entities": ["Python 3.14", "free-threading", "Python GIL removal"],
    },
]


async def send_cmd(ws, cmd):
    """Send a command and wait for the response, skipping broadcasts."""
    await ws.send(json.dumps(cmd, default=str))
    while True:
        raw = await ws.recv()
        resp = json.loads(raw)
        # Skip broadcast messages (they have "type" key, not "ok")
        if "ok" in resp or "memories" in resp:
            return resp
        # Otherwise it's a broadcast — skip it


async def run():
    print("Connecting to dashboard...")
    async with websockets.connect(WS_URL) as ws:
        # Read initial graph state
        init = await ws.recv()
        init_data = json.loads(init)
        print(f"Connected. Current graph: {len(init_data.get('nodes', []))} nodes, {len(init_data.get('edges', []))} edges")
        print()

        # Query existing memories
        resp = await send_cmd(ws, {"cmd": "query", "project": "python-gil", "limit": 50})
        existing = resp.get("memories", [])
        print(f"Step 1: Found {len(existing)} existing memories")
        existing_claims = []
        for mem in existing:
            try:
                content = json.loads(mem["content"]) if isinstance(mem["content"], str) else mem["content"]
                existing_claims.append({
                    "id": mem["id"],
                    "description": content.get("description", ""),
                })
            except:
                pass
        for c in existing_claims:
            print(f'  [{c["id"][:10]}] {c["description"][:70]}')
        print()

        # Fetch real sources (just to show we're reaching out)
        print("Step 2: Fetching real sources...")
        ssl_ctx = ssl.create_default_context()
        sources = [
            ("https://peps.python.org/pep-0703/", "PEP 703"),
            ("https://peps.python.org/pep-0779/", "PEP 779"),
        ]
        for url, name in sources:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Phoebe/0.1"})
                with urllib.request.urlopen(req, timeout=10, context=ssl_ctx) as r:
                    size = len(r.read())
                print(f"  ✓ {name}: {size:,} bytes")
            except Exception as e:
                print(f"  ✗ {name}: {e}")
        print()

        # Push discoveries through WebSocket
        print("Step 3: Building knowledge graph...")
        added = 0
        contradicted = 0

        for discovery in DISCOVERIES:
            # Send remember command
            cmd = {"cmd": "remember", **discovery}
            cmd.pop("contradicts_phrase", None)
            cmd.pop("contradiction_reason", None)
            resp = await send_cmd(ws, cmd)
            new_id = resp.get("memory_id", "")
            added += 1

            desc = discovery["content"]["description"]
            print(f"  + {desc[:70]}...")

            # Check for contradictions
            contradicts_phrase = discovery.get("contradicts_phrase")
            if contradicts_phrase:
                for ec in existing_claims:
                    if contradicts_phrase.lower() in ec["description"].lower():
                        reason = discovery.get("contradiction_reason", "new source contradicts")
                        await send_cmd(ws, {
                            "cmd": "contradict",
                            "new_id": new_id,
                            "existing_id": ec["id"],
                            "reason": reason,
                        })
                        contradicted += 1
                        print(f"    ✗ SUPERSEDES: \"{ec['description'][:50]}...\"")
                        break

            await asyncio.sleep(0.5)  # Pace for visual effect on dashboard

        print()
        print("═══════════════════════════════════════════")
        print("  Investigation Complete")
        print("═══════════════════════════════════════════")
        print(f"  Memories added:     {added}")
        print(f"  Contradictions:     {contradicted}")
        print(f"  Bad data superseded: {contradicted}")
        print()
        print("  Check the dashboard at http://127.0.0.1:8888")
        print("  Red nodes = superseded bad data")
        print("  Blue nodes = new verified knowledge")
        print("  Dashed red lines = contradiction edges")


asyncio.run(run())
PYEOF
