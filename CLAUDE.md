# Phoebe

Multimodal knowledge engine — stores memories as graph nodes, not files. Part of the Othrys Titan ecosystem.

## Quick Reference

```bash
# Install
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Test
pytest tests/

# Run MCP server
phoebe

# Run dashboard
./start.sh           # opens http://127.0.0.1:8888
```

## Architecture

- **Graph DB:** Kuzu (via `ladybugdb`) — 4 node tables (memories, entities, sources, plans), 15 edge types, BM25 full-text search index
- **Server:** FastMCP — 12 tools exposed over MCP
- **Dashboard:** FastAPI + WebSocket live graph visualizer
- **Dual mode:** Standalone (own `.tome` file) or inside Othrys (shared graph via `conn` parameter)

## Project Layout

```
src/phoebe/
  server.py          # FastMCP entry point, tool registration
  tome.py            # Tome lifecycle (create, open, close, stats)
  store.py           # Graph CRUD operations
  schema.py          # Kuzu schema definition
  models.py          # Data factories (make_memory, make_source, etc.)
  reasoning.py       # Graph traversals (causal chains, blast radius)
  investigate.py     # Investigation/correction logic
  tools/             # One file per MCP tool
    _shared.py       # get_store(), get_reasoner() helpers
    recall.py        # BM25 full-text search — the core query tool
    remember.py      # Store memories with provenance
    trace.py         # Walk causal chains
    brief.py         # Context briefs
    blast_radius.py  # Impact analysis
    who_knows.py     # Expertise detection
    stats.py         # Tome statistics
    create_plan.py   # Plan creation
    add_epic.py      # Epic management
    add_story.py     # Story management
    update_story.py  # Story updates
    get_plan.py      # Plan retrieval
  dashboard/
    app.py           # FastAPI + WebSocket live visualizer
tests/
  test_tome.py              # Core tests (schema, CRUD, edges, reasoning)
  test_ab_investigate.py    # Investigation + correction tests
  ab_test_gil.py            # A/B benchmark (7 GIL questions)
```

## Conventions

- Python 3.11+, Apache 2.0 license
- All tool handlers are plain `def` (not `async def`) — FastMCP runs them in a thread pool. Never use `async def` with sync calls inside; it blocks the event loop.
- Each tool lives in its own file under `tools/`. Shared helpers go in `tools/_shared.py`.
- Tool functions accept an optional `conn` parameter — when `None`, they open Phoebe's own tome; when provided (Othrys mode), they use the shared Kuzu connection.
- No linter/formatter configured. Keep code consistent with existing style.
- Graph node IDs use `m-<uuid>` prefix for memories, `s-<uuid>` for sources, `e-<name>` for entities.
- `.tome` files are Kuzu databases — excluded from git via `.gitignore`.
