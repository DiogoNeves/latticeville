# 🏘️ Latticeville — Project + Technical Spec

# Summary
Latticeville is a local-only, terminal-UI simulation of a tiny world with
LLM-driven characters. The goal is to reproduce the core *memory-first* loop
from the Generative Agents paper in a minimal, testable system. The simulation
engine and viewer remain strictly separated. 🧱🤖

# Project Goals
- Implement a small, clear agent loop: perceive → remember → retrieve → act.
- Prioritize memory systems and long-horizon behavior over visuals.
- Keep the UI terminal-only (ASCII) and simple to run locally.
- Maintain separation between simulation (model) and rendering (view).

# Non-Goals (for now)
- No web UI or replay website.
- No networked dependencies or telemetry.
- No complex world building, large maps, or multi-agent planning.
- No full-featured dialogue system (basic action text only).

# Scope
- Many agents (target ~10) with a minimal memory loop.
- Discrete tick-based scheduler.
- Terminal debug viewer that prints state (pretty UI later).
- One behavioral variable (energy or curiosity).
- Replay support: record tick-based changes or events to a local log.

# Technical Spec

## Architecture
- `latticeville/sim/` contains world state, agents, and tick logic.
- `latticeville/render/` contains terminal rendering only.
- The renderer accepts state and returns output; no mutation.
- `latticeville/db/` optionally holds persistence for memories and replay logs (defer for v1).
- `latticeville/llm/` holds local LLM adapters and prompt helpers.

## World Model (tree, paper-aligned)
- World is a tree of areas and objects (root = world, children = areas, leaves = objects).
- Each node has: `id`, `name`, `type` (`area`, `object`, `agent`), `parent_id`,
  and ordered `children`.
- Agents live in the tree as nodes with a current location (parent).
- Each agent maintains a **personal subtree / belief view** for locations and objects it knows.
- Agent belief views may diverge temporarily from the canonical world state (stale/partial),
  but follow the same structural schema (tree of nodes + containment).
- Perception uses the current area node and its immediate children.
- State is deterministic given the initial seed and actions.

## Core Agent Loop (per tick)
1. **Perceive** local environment (nearby objects + agents within visual range).
2. **Record observations** into memory stream:
   - Agent's own actions (what the agent did)
   - Other agents' actions (behaviors observed from nearby agents)
   - Object state changes (e.g., "refrigerator is empty", "stove is burning")
   - Inter-agent interactions (conversations, encounters)
3. **Retrieve** relevant memories using a scored subset.
4. **Decide** whether to react or follow current plan.
5. **Act** (single action description + optional location change).
6. **Write back** action and any reflections/plans into memory.

## Memory Stream
Each memory record is an append-only entry with:
- `description` (text)
- `created_at` (tick)
- `last_accessed_at` (tick)
- `importance` (1–10)
- `type` (`observation`, `plan`, `reflection`, `action`)
- Optional `location_id` (when the memory is grounded in a place)
- `links` to supporting records (for reflections)

### What gets recorded as observations
Observations are direct perceptions recorded each tick:
- **Agent's own actions**: "Isabella Rodriguez is setting out the pastries"
- **Other agents' actions**: "Maria Lopez is studying for a Chemistry test while drinking coffee"
- **Object states**: "The refrigerator is empty", "The stove is burning"
- **Inter-agent interactions**: "Isabella Rodriguez and Maria Lopez are conversing about planning a Valentine's day party"

The agent's own action (from step 5 of the loop) is also recorded, typically as an `action` type memory or as an observation of self.

### Location notes / annotations
- Agents can attach lightweight *annotations* to locations (e.g., "The cafe is usually crowded").
- These can be modeled as memories with `type=annotation` (or a dedicated table/stream),
  typically with a `location_id`.

### Retrieval Scoring (paper-aligned, minimal)
Score = recency + relevance + importance, normalized to [0, 1].
- **Recency** decays exponentially since last access.
- **Relevance** can start as simple keyword overlap; embeddings optional.
- **Importance** assigned at creation time (LLM or heuristic).

Select top-k memories that fit the context window.

## Reflection (optional for v1)
- Trigger when total importance of recent memories crosses a threshold.
- Generate 1–3 insights and store as reflections.
- Link reflections to supporting memories.

## Planning (minimal)
- Daily plan optional; start with short, single-step intentions.
- If a reaction occurs, it can override the current plan.

## LLM Usage (local only)
- Use local models via adapters (Ollama/MLX/vLLM).
- Prompts should be short and deterministic where possible.
- Avoid external APIs.

## Rendering (terminal)
- For v1, rendering is a debug view that outputs simulation state per tick (pretty later).
- Multiple viewers should be attachable (e.g., one prints summary, one logs JSON, one draws ASCII).
- Viewers are tick-synchronized: they see whole-tick snapshots/events only (no partial updates).
- Any future simulator inputs (pause/step/commands) must enter as explicit simulator inputs,
  applied only at tick boundaries.
- Replay is event-sourced with periodic snapshots (see [Architecture](thinking/architecture.md)).

# Questions / Open Decisions
- Choose the single behavioral variable: energy or curiosity?
- Should relevance use embeddings or simple keyword overlap for v1?
- Should reflections be included in the first milestone or deferred?
- What exactly goes into `TickPayload`: which parts of canonical state vs belief summaries?
- Should we standardize events early (e.g., `MOVE(agent_id, from, to)`) or keep free-text?

# References
- Paper Abstract: https://arxiv.org/abs/2304.03442
- Paper PDF: https://arxiv.org/pdf/2304.03442