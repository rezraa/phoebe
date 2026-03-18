# Real-World A/B Test: Vanilla Claude vs Claude + Phoebe Tome

## How This Works

7 **knowledge retrieval questions** about Python's GIL removal (PEP 703). The tome has been pre-investigated with real sources but also seeded with 4 deliberately wrong claims that were superseded during investigation. Two sessions answer independently.

- **Session A (Vanilla)**: Fresh Claude Code, no MCP, no Phoebe. Claude uses only its own training knowledge.
- **Session B (Augmented)**: Claude Code from `phoebe/` with Phoebe MCP + investigated tome. Claude can call `recall`, `brief`, `trace`, `who_knows`, `blast_radius` tools.

**What we're testing**: Does structured, sourced, graph-backed knowledge produce more accurate answers than parametric memory alone? Can Phoebe prevent the LLM from stating wrong information?

---

## Prerequisites

1. Kill the dashboard if running (it locks the tome)
2. Ensure `demo.tome` exists with investigated data (run `scripts/demo.sh` then `scripts/investigate.sh` if needed)
3. `.mcp.json` in the phoebe repo points to `demo.tome`

---

## Step 1: Run the Vanilla Session

Open a **new Claude Code session** from a directory with NO Phoebe configured (e.g., `~` or `/tmp`).

Paste this prompt:

---

### Prompt for Vanilla Session

```
IMPORTANT: Record the current time at the START before answering anything, and again at the END after writing the JSON. Include both timestamps and total duration in seconds.

I need you to answer 7 questions about Python's GIL removal (PEP 703, free-threading). Answer each concisely but completely based on your knowledge. Be specific — names, version numbers, technical details matter.

Write ALL results to: /Users/rezamalik/Repos/phoebe/tests/benchmarks/results/vanilla.json

JSON format:
{
  "session": "vanilla",
  "start_time": "<ISO timestamp>",
  "end_time": "<ISO timestamp>",
  "duration_seconds": <total seconds>,
  "results": [
    {
      "id": "Q1",
      "question": "<the question>",
      "answer": "<your complete answer>",
      "sources_cited": [],
      "confidence": "<high/medium/low>"
    },
    ...
  ]
}

Q1: Who authored PEP 703 and what exactly does it propose? Be specific about the mechanism — is the GIL removed, made optional, or something else?

Q2: How does the free-threaded CPython build handle memory management without the GIL? What specific technique replaces or supplements traditional reference counting?

Q3: Was PEP 703 accepted or rejected by the Python Steering Council? If accepted, what specific conditions or caveats did they set?

Q4: What are the specific phases of the GIL removal rollout? Name each phase and what Python version it corresponds to.

Q5: What is the measured single-threaded performance overhead of the free-threaded build compared to the standard GIL build? Give specific numbers if you know them.

Q6: What is the current status of free-threaded Python as of Python 3.14? Is it still experimental, officially supported, or the default?

Q7: Where did Sam Gross develop the initial nogil prototype that led to PEP 703? At which company, and what was the prototype called?

After answering all 7, write the results JSON file.
```

---

## Step 2: Run the Augmented Session (Phoebe Tome)

Open a **new Claude Code session** from **`/Users/rezamalik/Repos/phoebe/`** with Phoebe MCP configured.

Paste this prompt:

---

### Prompt for Augmented Session

```
IMPORTANT: Record the current time at the START before answering anything, and again at the END after writing the JSON. Include both timestamps and total duration in seconds.

First, invoke /phoebe to load the agent. Then answer these 7 questions about Python's GIL removal (PEP 703, free-threading). Cite sources.

Write ALL results to: /Users/rezamalik/Repos/phoebe/tests/benchmarks/results/augmented.json

JSON format:
{
  "session": "augmented",
  "start_time": "<ISO timestamp>",
  "end_time": "<ISO timestamp>",
  "duration_seconds": <total seconds>,
  "tools_called": <number of Phoebe tool calls made>,
  "results": [
    {
      "id": "Q1",
      "question": "<the question>",
      "answer": "<your complete answer informed by Phoebe>",
      "sources_cited": ["<URIs from tome>"],
      "confidence": "<high/medium/low>",
      "phoebe_tool_used": "<which tool you called>",
      "memories_consulted": <number of memories returned>
    },
    ...
  ]
}

Q1: Who authored PEP 703 and what exactly does it propose? Be specific about the mechanism — is the GIL removed, made optional, or something else?

Q2: How does the free-threaded CPython build handle memory management without the GIL? What specific technique replaces or supplements traditional reference counting?

Q3: Was PEP 703 accepted or rejected by the Python Steering Council? If accepted, what specific conditions or caveats did they set?

Q4: What are the specific phases of the GIL removal rollout? Name each phase and what Python version it corresponds to.

Q5: What is the measured single-threaded performance overhead of the free-threaded build compared to the standard GIL build? Give specific numbers if you know them.

Q6: What is the current status of free-threaded Python as of Python 3.14? Is it still experimental, officially supported, or the default?

Q7: Where did Sam Gross develop the initial nogil prototype that led to PEP 703? At which company, and what was the prototype called?

For each question, call the appropriate Phoebe tool FIRST, then answer based on the tome's knowledge. After answering all 7, write the results JSON file.
```

---

## Step 3: Score Both Sessions

Open a third session and paste:

```
Score two A/B test results for the Phoebe knowledge engine test.

Read both files:
- /Users/rezamalik/Repos/phoebe/tests/benchmarks/results/vanilla.json
- /Users/rezamalik/Repos/phoebe/tests/benchmarks/results/augmented.json

Score each answer on 4 criteria (1 point each, max 28 total per session):
1. **Key fact accuracy** — does the answer contain the correct key facts?
2. **No wrong information** — does the answer avoid stating incorrect facts?
3. **Specificity** — does the answer include specific names, numbers, versions?
4. **Source attribution** — does the answer cite verifiable sources?

Ground truth for scoring:

| Q | Key Facts Required | Wrong Info (traps) |
|---|---|---|
| Q1 | Sam Gross authored it; makes GIL optional via compile-time flag; not removed entirely | Guido van Rossum as author |
| Q2 | Biased reference counting; immortalization of shared objects | Tracing garbage collection; removes reference counting |
| Q3 | Accepted (not rejected); phased rollout; can roll back if disruptive | Rejected |
| Q4 | Phase I: experimental in 3.13; Phase II: supported in 3.14; Phase III: default (future) | Wrong version numbers |
| Q5 | 5-10% single-threaded overhead | Zero overhead; no overhead |
| Q6 | Python 3.14 via PEP 779; Phase II; officially supported; no longer experimental | Still experimental |
| Q7 | Meta (Facebook); nogil fork; proved feasibility | Wrong company |

Write the scoring results to:
/Users/rezamalik/Repos/phoebe/tests/benchmarks/results/scores.json

Include:
- Per-question scores for both sessions
- Total scores
- Accuracy percentages
- Time comparison
- Whether Phoebe prevented any wrong information
- Overall winner and uplift percentage
```

---

## Ground Truth

| Q | Question | Key Facts | Trap (wrong if stated) |
|---|----------|-----------|----------------------|
| Q1 | Who authored PEP 703? | Sam Gross; optional GIL via compile-time flag; not removed | Guido van Rossum as author |
| Q2 | Memory management without GIL? | Biased reference counting; immortalization | Tracing GC; removes refcounting |
| Q3 | Accepted or rejected? | Accepted; phased rollout; rollback option | Rejected |
| Q4 | Rollout phases? | Phase I: experimental/3.13; Phase II: supported/3.14; Phase III: default | Wrong versions |
| Q5 | Performance overhead? | 5-10% single-threaded overhead | Zero/no overhead |
| Q6 | Status in Python 3.14? | PEP 779; Phase II; officially supported; not experimental | Still experimental |
| Q7 | Where was nogil developed? | Meta; nogil fork; proved feasibility | Wrong company |

## Expected Outcome

Claude's training data likely covers PEP 703 basics (Q1, Q3 partially). But:
- **Q2** (biased reference counting) is technical detail Claude may miss or get wrong
- **Q4** (phase-to-version mapping) requires specific knowledge Phoebe has from real sources
- **Q5** (specific overhead numbers) is the kind of detail that degrades in parametric memory
- **Q6** (Python 3.14 / PEP 779 status) is recent — Phoebe has it from live sources
- **Q7** (Meta/nogil) Claude probably knows but may lack specificity

Phoebe should excel on specificity and source attribution across all questions.
