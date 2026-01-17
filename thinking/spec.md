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
- One character with a minimal memory loop.
- Discrete tick-based scheduler.
- ASCII-only rendering in terminal.
- One behavioral variable (energy or curiosity).
- Optional: write replay logs to a local file.

# Technical Spec

## Architecture
- `latticeville/sim/` contains world state, agents, and tick logic.
- `latticeville/render/` contains terminal rendering only.
- The renderer accepts state and returns output; no mutation.
- `latticeville/db/` holds SQLite persistence for memories and replay logs.
- `latticeville/llm/` holds local LLM adapters and prompt helpers.

## World Model (tree, paper-aligned)
- World is a tree of areas and objects (root = world, children = areas, leaves = objects).
- Each node has: `id`, `name`, `type` (`area`, `object`, `agent`), `parent_id`,
  and ordered `children`.
- Agents live in the tree as nodes with a current location (parent).
- Each agent maintains a **personal subtree** for locations it knows.
- Perception uses the current area node and its immediate children.
- State is deterministic given the initial seed and actions.

## Core Agent Loop (per tick)
1. **Perceive** local environment (nearby objects + agents).
2. **Record** observations into memory stream.
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
- `links` to supporting records (for reflections)

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
- Layout with a world panel and a context panel (agent state + recent memory).
- No input handling required for v1.

# Questions / Open Decisions
- Choose the single behavioral variable: energy or curiosity?
- Should relevance use embeddings or simple keyword overlap for v1?
- Should reflections be included in the first milestone or deferred?

# References
- Paper Abstract: https://arxiv.org/abs/2304.03442
- Paper PDF: https://arxiv.org/pdf/2304.03442