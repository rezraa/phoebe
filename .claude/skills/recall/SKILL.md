# Phoebe — Workflow

## Input

The user will provide: $ARGUMENTS

This could be a question, a topic to research, or a request for project context.

## Workflow

### If answering a question:

1. **RECALL** from your tome. Call `recall` with:
   - `query`: the topic (try multiple terms if first returns empty, e.g. "GIL removal", "PEP 703", "free-threading")
   - `project`: project name if known

2. **CHECK** what came back:
   - If memories exist → go to step 5
   - If empty or insufficient → go to step 3

3. **LEARN** from the web. This is critical — don't skip this:
   - Use web search to find authoritative primary sources on the topic
   - Use web fetch to read each source (you see content natively)
   - For EACH key fact you extract, **CALL** `remember` with:
     - `content`: the fact (concise, one claim per memory)
     - `memory_type`: "decision", "context", "observation", "risk", "lesson", etc.
     - `source_uri`: the URL you found it at
     - `source_type`: "url"
     - `entities`: list of key names mentioned (people, systems, projects, standards)
     - `confidence`: 0.9 for official docs/PEPs, 0.7 for blog posts, 0.5 for forums

4. **VERIFY** against existing memories:
   - If new facts contradict existing memories, the newer sourced fact wins
   - If new facts confirm existing memories, note the corroboration

5. **ANSWER** the question using your tome memories. For each claim in your answer:
   - Cite the source URI
   - Note the confidence level
   - If memories were just learned (step 3), say so

### If building a tome on a new topic:

1. **RECALL** to check what's already known
2. **SEARCH** broadly — find 3-5 authoritative sources
3. **READ** each source
4. **REMEMBER** every key fact (call `remember` for each one)
5. **SUMMARIZE** what the tome now knows

### If checking project context:

1. **CALL** `brief` with the project name and optional topic
2. **INTERPRET** the brief: decisions, open questions, failed approaches, assumptions
3. **ANSWER** with the full context

## Always

- Call the tools — that's the whole point. Don't just answer from your own training.
- When recall is empty, LEARN first, REMEMBER what you learn, THEN answer.
- Show what you recalled or learned and cite the sources.
- The tome grows every time you learn. That's the value.
