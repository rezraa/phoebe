# Copyright (c) 2026 Reza Malik. Licensed under the Apache License, Version 2.0.
"""Phoebe Dashboard — Live graph visualization during investigation.

Serves a web UI that shows the knowledge graph growing in real-time.
Nodes appear, edges connect, contradictions glow red, corroborations green.

Usage:
    python -m phoebe.dashboard.app [tome_path]
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from phoebe.tome import Tome
from phoebe.store import GraphStore

app = FastAPI(title="Phoebe — Knowledge Graph Visualizer")

# Global state
_connections: list[WebSocket] = []
_tome: Tome | None = None
_store: GraphStore | None = None


async def broadcast(event: dict) -> None:
    """Send event to all connected WebSocket clients."""
    data = json.dumps(event, default=str)
    for ws in _connections[:]:
        try:
            await ws.send_text(data)
        except Exception:
            _connections.remove(ws)


def get_full_graph(store: GraphStore) -> dict:
    """Export the entire graph as nodes + edges for visualization."""
    conn = store._conn
    nodes = []
    edges = []

    # Memories
    result = conn.execute("MATCH (m:memories) RETURN m")
    while result.has_next():
        row = result.get_next()
        m = row[0]
        content = m.get("content", "{}")
        try:
            desc = json.loads(content).get("description", content[:80]) if isinstance(content, str) else str(content)[:80]
        except (json.JSONDecodeError, TypeError):
            desc = str(content)[:80]

        color = "#ef4444" if m.get("status") == "superseded" else "#3b82f6"
        if "CORRECTION" in desc:
            color = "#f59e0b"

        nodes.append({
            "id": m["id"],
            "label": desc[:50],
            "type": "memory",
            "subtype": m.get("memory_type", ""),
            "status": m.get("status", ""),
            "confidence": m.get("confidence", 0),
            "color": color,
            "size": 20,
        })

    # Sources
    result = conn.execute("MATCH (s:sources) RETURN s")
    while result.has_next():
        row = result.get_next()
        s = row[0]
        color = "#ef4444" if s.get("stale") else "#10b981"
        nodes.append({
            "id": s["id"],
            "label": s.get("name", s.get("uri", ""))[:40],
            "type": "source",
            "subtype": s.get("source_type", ""),
            "stale": s.get("stale", False),
            "color": color,
            "size": 15,
        })

    # Entities
    result = conn.execute("MATCH (e:entities) RETURN e")
    while result.has_next():
        row = result.get_next()
        e = row[0]
        nodes.append({
            "id": e["id"],
            "label": e.get("name", "")[:30],
            "type": "entity",
            "subtype": e.get("entity_type", ""),
            "color": "#8b5cf6",
            "size": 18,
        })

    # Milestones
    result = conn.execute("MATCH (ms:milestones) RETURN ms")
    while result.has_next():
        row = result.get_next()
        ms = row[0]
        nodes.append({
            "id": ms["id"],
            "label": ms.get("name", "")[:30],
            "type": "milestone",
            "subtype": ms.get("milestone_type", ""),
            "color": "#f97316",
            "size": 16,
        })

    # Edges — query each relationship type
    edge_queries = [
        ("caused_by", "memories", "memories", "#ff6b6b", "caused by"),
        ("supersedes", "memories", "memories", "#ef4444", "supersedes"),
        ("contradicts", "memories", "memories", "#ef4444", "contradicts"),
        ("corroborates", "memories", "memories", "#10b981", "corroborates"),
        ("blocked_by", "memories", "memories", "#f59e0b", "blocked by"),
        ("extracted_from", "memories", "sources", "#6b7280", "from"),
        ("about", "memories", "entities", "#8b5cf6", "about"),
        ("decided_by", "memories", "entities", "#3b82f6", "decided by"),
        ("affects", "memories", "entities", "#f59e0b", "affects"),
        ("occurred_during", "memories", "milestones", "#f97316", "during"),
        ("depends_on", "entities", "entities", "#ef4444", "depends on"),
        ("owns", "entities", "entities", "#3b82f6", "owns"),
        ("contains", "sources", "sources", "#6b7280", "contains"),
        ("related_to", "entities", "entities", "#6b7280", "related"),
        ("introduced_in", "entities", "milestones", "#10b981", "introduced"),
        ("deprecated_in", "entities", "milestones", "#ef4444", "deprecated"),
    ]

    for rel_name, from_table, to_table, color, label in edge_queries:
        try:
            result = conn.execute(
                f"MATCH (a:{from_table})-[r:{rel_name}]->(b:{to_table}) RETURN a.id, b.id"
            )
            while result.has_next():
                row = result.get_next()
                edges.append({
                    "source": row[0],
                    "target": row[1],
                    "type": rel_name,
                    "label": label,
                    "color": color,
                })
        except Exception:
            pass  # Table might not exist yet

    return {"nodes": nodes, "edges": edges}


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


@app.get("/api/graph")
async def api_graph():
    if _store is None:
        return {"nodes": [], "edges": []}
    return get_full_graph(_store)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _connections.append(websocket)
    try:
        # Send full graph on connect
        if _store:
            graph = get_full_graph(_store)
            await websocket.send_text(json.dumps({"type": "full_graph", **graph}, default=str))
        while True:
            raw = await websocket.receive_text()
            # Handle commands from investigate script
            try:
                msg = json.loads(raw)
                cmd = msg.get("cmd")
                if cmd and _store:
                    result = await _handle_command(msg)
                    await websocket.send_text(json.dumps(result, default=str))
            except (json.JSONDecodeError, TypeError):
                pass
    except WebSocketDisconnect:
        if websocket in _connections:
            _connections.remove(websocket)


async def _handle_command(msg: dict) -> dict:
    """Handle a command from the investigate script via WebSocket."""
    from phoebe.models import make_memory, make_source, make_entity
    cmd = msg["cmd"]

    if cmd == "remember":
        mem = make_memory(
            content=msg.get("content", {}),
            memory_type=msg.get("memory_type", "observation"),
            project=msg.get("project", ""),
            confidence=msg.get("confidence", 0.8),
            status=msg.get("status", "open"),
            outcome=msg.get("outcome", "unknown"),
        )
        mid = _store.add_memory(mem)

        source_id = ""
        if msg.get("source_uri"):
            src = make_source(
                uri=msg["source_uri"],
                source_type=msg.get("source_type", "url"),
                name=msg.get("source_name", ""),
            )
            source_id = _store.get_or_create_source(src)
            _store.link_memory_to_source(mid, source_id)

        entity_ids = []
        for ename in msg.get("entities", []):
            ent = make_entity(name=ename, entity_type="system")
            eid = _store.get_or_create_entity(ent)
            _store.link_memory_to_entity(mid, eid, "about")
            entity_ids.append(eid)

        graph = get_full_graph(_store)
        await broadcast({"type": "full_graph", **graph})
        return {"ok": True, "memory_id": mid, "source_id": source_id, "entities": entity_ids}

    elif cmd == "contradict":
        existing_id = msg.get("existing_id", "")
        new_id = msg.get("new_id", "")
        reason = msg.get("reason", "")
        if existing_id and new_id:
            _store.link_memories_contradict(new_id, existing_id, reason)
            _store.update_memory_status(existing_id, "superseded")
            graph = get_full_graph(_store)
            await broadcast({"type": "full_graph", **graph})
            return {"ok": True, "superseded": existing_id}
        return {"ok": False, "error": "missing ids"}

    elif cmd == "corroborate":
        id_a = msg.get("id_a", "")
        id_b = msg.get("id_b", "")
        if id_a and id_b:
            _store.link_memories_corroborate(id_a, id_b)
            graph = get_full_graph(_store)
            await broadcast({"type": "full_graph", **graph})
            return {"ok": True}
        return {"ok": False, "error": "missing ids"}

    elif cmd == "query":
        memories = _store.query_memories(
            project=msg.get("project") or None,
            limit=msg.get("limit", 50),
        )
        return {"ok": True, "memories": memories}

    return {"ok": False, "error": f"unknown cmd: {cmd}"}


# ---------------------------------------------------------------------------
# HTML + JS — Single file, no build step
# ---------------------------------------------------------------------------

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Phoebe — Knowledge Graph</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #0f172a; color: #e2e8f0; font-family: 'SF Mono', 'Fira Code', monospace; overflow: hidden; }
#header {
    position: fixed; top: 0; left: 0; right: 0; z-index: 10;
    padding: 12px 20px; background: rgba(15, 23, 42, 0.9);
    border-bottom: 1px solid #1e293b; backdrop-filter: blur(8px);
    display: flex; align-items: center; justify-content: space-between;
}
#header h1 { font-size: 16px; color: #8b5cf6; }
#header h1 span { color: #64748b; font-weight: normal; }
#stats {
    display: flex; gap: 20px; font-size: 12px; color: #94a3b8;
}
.stat-value { color: #e2e8f0; font-weight: bold; }
#canvas { width: 100vw; height: 100vh; display: block; }
#legend {
    position: fixed; bottom: 20px; left: 20px; z-index: 10;
    background: rgba(15, 23, 42, 0.9); border: 1px solid #1e293b;
    border-radius: 8px; padding: 12px 16px; font-size: 11px;
    backdrop-filter: blur(8px);
}
.legend-item { display: flex; align-items: center; gap: 8px; margin: 4px 0; }
.legend-dot { width: 10px; height: 10px; border-radius: 50%; }
#tooltip {
    position: fixed; display: none; z-index: 20;
    background: rgba(30, 41, 59, 0.95); border: 1px solid #334155;
    border-radius: 6px; padding: 10px 14px; font-size: 12px;
    max-width: 350px; pointer-events: none; backdrop-filter: blur(4px);
}
#tooltip .tt-type { color: #8b5cf6; font-size: 10px; text-transform: uppercase; }
#tooltip .tt-label { color: #e2e8f0; margin: 4px 0; }
#tooltip .tt-meta { color: #64748b; font-size: 10px; }
#activity {
    position: fixed; top: 60px; right: 20px; z-index: 10;
    width: 300px; max-height: 400px; overflow-y: auto;
    background: rgba(15, 23, 42, 0.9); border: 1px solid #1e293b;
    border-radius: 8px; padding: 12px; font-size: 11px;
    backdrop-filter: blur(8px);
}
#activity h3 { color: #8b5cf6; margin-bottom: 8px; font-size: 12px; }
.activity-item {
    padding: 6px 0; border-bottom: 1px solid #1e293b;
    animation: fadeIn 0.3s ease-in;
}
.activity-item:last-child { border-bottom: none; }
.act-add { color: #10b981; }
.act-supersede { color: #ef4444; }
.act-contradict { color: #f59e0b; }
.act-corroborate { color: #10b981; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(-5px); } to { opacity: 1; transform: translateY(0); } }
@keyframes pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.3); } }
.node-new { animation: pulse 0.6s ease-out; }
</style>
</head>
<body>
<div id="header">
    <h1>Phoebe <span>— Knowledge Graph</span></h1>
    <div id="stats">
        <span>Memories: <span class="stat-value" id="stat-memories">0</span></span>
        <span>Sources: <span class="stat-value" id="stat-sources">0</span></span>
        <span>Entities: <span class="stat-value" id="stat-entities">0</span></span>
        <span>Edges: <span class="stat-value" id="stat-edges">0</span></span>
        <span>Superseded: <span class="stat-value" id="stat-superseded" style="color:#ef4444">0</span></span>
    </div>
</div>

<canvas id="canvas"></canvas>

<div id="legend">
    <div class="legend-item"><div class="legend-dot" style="background:#3b82f6"></div> Memory (active)</div>
    <div class="legend-item"><div class="legend-dot" style="background:#ef4444"></div> Memory (superseded)</div>
    <div class="legend-item"><div class="legend-dot" style="background:#f59e0b"></div> Correction</div>
    <div class="legend-item"><div class="legend-dot" style="background:#10b981"></div> Source (verified)</div>
    <div class="legend-item"><div class="legend-dot" style="background:#8b5cf6"></div> Entity</div>
    <div class="legend-item"><div class="legend-dot" style="background:#f97316"></div> Milestone</div>
    <div style="margin-top:8px; border-top:1px solid #1e293b; padding-top:6px">
    <div class="legend-item" style="color:#10b981">── corroborates</div>
    <div class="legend-item" style="color:#ef4444">── contradicts / supersedes</div>
    <div class="legend-item" style="color:#6b7280">── from / about / related</div>
    </div>
</div>

<div id="activity">
    <h3>Activity Feed</h3>
    <div id="feed"></div>
</div>

<div id="tooltip">
    <div class="tt-type"></div>
    <div class="tt-label"></div>
    <div class="tt-meta"></div>
</div>

<script>
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const tooltip = document.getElementById('tooltip');
const feed = document.getElementById('feed');

let nodes = [];
let edges = [];
let nodeMap = {};
let hoveredNode = null;
let dragNode = null;
let offsetX = 0, offsetY = 0;
let panX = 0, panY = 0, zoom = 1;
let lastMouse = {x: 0, y: 0};
let isPanning = false;

function resize() {
    canvas.width = window.innerWidth * devicePixelRatio;
    canvas.height = window.innerHeight * devicePixelRatio;
    canvas.style.width = window.innerWidth + 'px';
    canvas.style.height = window.innerHeight + 'px';
    ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
}
window.addEventListener('resize', resize);
resize();

function addNode(node) {
    if (nodeMap[node.id]) {
        Object.assign(nodeMap[node.id], node);
        return;
    }
    node.x = window.innerWidth/2 + (Math.random()-0.5) * 400;
    node.y = window.innerHeight/2 + (Math.random()-0.5) * 400;
    node.vx = 0; node.vy = 0;
    node.age = 0;
    nodes.push(node);
    nodeMap[node.id] = node;
}

function addEdge(edge) {
    if (!edges.find(e => e.source === edge.source && e.target === edge.target && e.type === edge.type)) {
        edges.push(edge);
    }
}

function updateStats() {
    const mems = nodes.filter(n => n.type === 'memory');
    document.getElementById('stat-memories').textContent = mems.length;
    document.getElementById('stat-sources').textContent = nodes.filter(n => n.type === 'source').length;
    document.getElementById('stat-entities').textContent = nodes.filter(n => n.type === 'entity').length;
    document.getElementById('stat-edges').textContent = edges.length;
    document.getElementById('stat-superseded').textContent = mems.filter(n => n.status === 'superseded').length;
}

function addActivity(text, cls) {
    const div = document.createElement('div');
    div.className = 'activity-item ' + cls;
    div.textContent = text;
    feed.insertBefore(div, feed.firstChild);
    if (feed.children.length > 50) feed.removeChild(feed.lastChild);
}

// Force-directed layout
function simulate() {
    const k = 80;
    const gravity = 0.01;
    const cx = window.innerWidth / 2, cy = window.innerHeight / 2;

    for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i];
        if (a === dragNode) continue;
        // Gravity toward center
        a.vx += (cx - a.x) * gravity;
        a.vy += (cy - a.y) * gravity;
        // Repulsion
        for (let j = i+1; j < nodes.length; j++) {
            const b = nodes[j];
            let dx = a.x - b.x, dy = a.y - b.y;
            let d = Math.sqrt(dx*dx + dy*dy) || 1;
            let f = k * k / d;
            a.vx += dx/d * f * 0.05;
            a.vy += dy/d * f * 0.05;
            if (b !== dragNode) {
                b.vx -= dx/d * f * 0.05;
                b.vy -= dy/d * f * 0.05;
            }
        }
    }
    // Attraction along edges
    for (const e of edges) {
        const a = nodeMap[e.source], b = nodeMap[e.target];
        if (!a || !b) continue;
        let dx = b.x - a.x, dy = b.y - a.y;
        let d = Math.sqrt(dx*dx + dy*dy) || 1;
        let f = (d - k) * 0.005;
        if (a !== dragNode) { a.vx += dx/d * f; a.vy += dy/d * f; }
        if (b !== dragNode) { b.vx -= dx/d * f; b.vy -= dy/d * f; }
    }
    // Apply velocity with damping
    for (const n of nodes) {
        if (n === dragNode) continue;
        n.vx *= 0.85; n.vy *= 0.85;
        n.x += n.vx; n.y += n.vy;
        n.age++;
    }
}

function draw() {
    ctx.clearRect(0, 0, canvas.width / devicePixelRatio, canvas.height / devicePixelRatio);
    ctx.save();
    ctx.translate(panX, panY);
    ctx.scale(zoom, zoom);

    // Edges
    for (const e of edges) {
        const a = nodeMap[e.source], b = nodeMap[e.target];
        if (!a || !b) continue;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.strokeStyle = e.color || '#334155';
        ctx.lineWidth = e.type === 'contradicts' || e.type === 'supersedes' ? 2 : 1;
        if (e.type === 'contradicts') ctx.setLineDash([4,4]); else ctx.setLineDash([]);
        ctx.globalAlpha = 0.5;
        ctx.stroke();
        ctx.globalAlpha = 1;
        ctx.setLineDash([]);
    }

    // Nodes
    for (const n of nodes) {
        const r = (n.size || 15) * (hoveredNode === n ? 1.3 : 1);
        // Glow for new nodes
        if (n.age < 30) {
            ctx.beginPath();
            ctx.arc(n.x, n.y, r + 8, 0, Math.PI * 2);
            ctx.fillStyle = n.color + '33';
            ctx.fill();
        }
        // Node circle
        ctx.beginPath();
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
        ctx.fillStyle = n.color || '#3b82f6';
        ctx.globalAlpha = n.status === 'superseded' ? 0.4 : 0.9;
        ctx.fill();
        ctx.globalAlpha = 1;
        // Border
        if (hoveredNode === n) {
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 2;
            ctx.stroke();
        }
        // Label
        ctx.font = '10px SF Mono, Fira Code, monospace';
        ctx.fillStyle = '#94a3b8';
        ctx.textAlign = 'center';
        ctx.fillText(n.label || '', n.x, n.y + r + 14);
    }
    ctx.restore();
}

function loop() {
    simulate();
    draw();
    requestAnimationFrame(loop);
}
loop();

// Mouse interaction
canvas.addEventListener('mousemove', (e) => {
    const mx = (e.clientX - panX) / zoom;
    const my = (e.clientY - panY) / zoom;
    lastMouse = {x: e.clientX, y: e.clientY};

    if (dragNode) {
        dragNode.x = mx; dragNode.y = my;
        dragNode.vx = 0; dragNode.vy = 0;
        return;
    }
    if (isPanning) {
        panX += e.movementX; panY += e.movementY;
        return;
    }

    hoveredNode = null;
    for (const n of nodes) {
        const dx = n.x - mx, dy = n.y - my;
        if (Math.sqrt(dx*dx+dy*dy) < (n.size||15)) {
            hoveredNode = n;
            break;
        }
    }
    if (hoveredNode) {
        tooltip.style.display = 'block';
        tooltip.style.left = (e.clientX + 15) + 'px';
        tooltip.style.top = (e.clientY + 15) + 'px';
        tooltip.querySelector('.tt-type').textContent = hoveredNode.type + (hoveredNode.subtype ? ' / ' + hoveredNode.subtype : '');
        tooltip.querySelector('.tt-label').textContent = hoveredNode.label;
        const meta = [];
        if (hoveredNode.status) meta.push('status: ' + hoveredNode.status);
        if (hoveredNode.confidence) meta.push('confidence: ' + (hoveredNode.confidence * 100).toFixed(0) + '%');
        if (hoveredNode.stale) meta.push('⚠ STALE');
        tooltip.querySelector('.tt-meta').textContent = meta.join(' · ');
        canvas.style.cursor = 'pointer';
    } else {
        tooltip.style.display = 'none';
        canvas.style.cursor = 'default';
    }
});

canvas.addEventListener('mousedown', (e) => {
    const mx = (e.clientX - panX) / zoom;
    const my = (e.clientY - panY) / zoom;
    for (const n of nodes) {
        const dx = n.x - mx, dy = n.y - my;
        if (Math.sqrt(dx*dx+dy*dy) < (n.size||15)) {
            dragNode = n; return;
        }
    }
    isPanning = true;
});

canvas.addEventListener('mouseup', () => { dragNode = null; isPanning = false; });
canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    const factor = e.deltaY > 0 ? 0.9 : 1.1;
    zoom *= factor;
    panX = e.clientX - (e.clientX - panX) * factor;
    panY = e.clientY - (e.clientY - panY) * factor;
}, {passive: false});

// WebSocket — live updates
const ws = new WebSocket('ws://' + location.host + '/ws');
ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'full_graph') {
        (msg.nodes || []).forEach(n => addNode(n));
        (msg.edges || []).forEach(e => addEdge(e));
        updateStats();
        addActivity('Graph loaded: ' + nodes.length + ' nodes, ' + edges.length + ' edges', '');
    } else if (msg.type === 'node_added') {
        addNode(msg.node);
        updateStats();
        addActivity('+ ' + msg.node.label, 'act-add');
    } else if (msg.type === 'edge_added') {
        addEdge(msg.edge);
        updateStats();
        if (msg.edge.type === 'contradicts') addActivity('✗ contradicts: ' + msg.edge.label, 'act-contradict');
        else if (msg.edge.type === 'corroborates') addActivity('✓ corroborates', 'act-corroborate');
        else if (msg.edge.type === 'supersedes') addActivity('⟳ supersedes', 'act-supersede');
    } else if (msg.type === 'node_updated') {
        addNode(msg.node);
        updateStats();
        if (msg.node.status === 'superseded') addActivity('✗ superseded: ' + msg.node.label, 'act-supersede');
    }
};
ws.onclose = () => addActivity('Connection lost', '');

// Poll for updates (fallback)
setInterval(async () => {
    try {
        const r = await fetch('/api/graph');
        const g = await r.json();
        g.nodes.forEach(n => addNode(n));
        g.edges.forEach(e => addEdge(e));
        updateStats();
    } catch(e) {}
}, 3000);
</script>
</body>
</html>
"""


def run(tome_path: str | None = None, host: str = "127.0.0.1", port: int = 8888):
    """Start the dashboard server."""
    global _tome, _store
    import uvicorn

    path = Path(tome_path) if tome_path else None
    if path:
        _tome = Tome(path)
        _tome.open()
        _store = GraphStore(_tome.connection())
        print(f"Phoebe Dashboard — loaded tome: {path}")
        stats = _tome.stats()
        print(f"  memories: {stats['memories']}, sources: {stats['sources']}, "
              f"entities: {stats['entities']}, milestones: {stats['milestones']}")
    else:
        print("Phoebe Dashboard — no tome loaded (will show empty graph)")

    print(f"  → http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    tome_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(tome_arg)
