# 🏘️ Latticeville — Project + Technical Spec

# Summary

Latticeville is a local-only, terminal-UI simulation of a tiny cyberpunk neon village with LLM-driven characters. The main goal is to implement the core _memory-first_ loop from the Generative Agents paper using a fully local LLM system. 🧱🤖

**Note:** This spec reflects the intended final outcome of the project and does not encode the strategy or order in which it will be implemented.

# Project Goals

- Implement a small, clear agent loop: perceive → remember → retrieve → act.
- Support reflections: periodic synthesis of insights from accumulated memories.
- Prioritize memory systems and long-horizon behavior over visuals.
- Keep the UI terminal-only (ASCII) and simple to run locally.
- Maintain separation between simulation (model) and rendering (view).
- Support many agents (target ~10) with a minimal memory loop.
- Use a discrete tick-based scheduler.
- Provide a terminal debug viewer that prints state.
- Include replay support: record tick-based changes and events to a local log.

# Non-Goals

- No web UI or replay website.
- No networked dependencies or telemetry.
- No complex world building or very large maps.

# Technical Spec

## Architecture

- `latticeville/sim/` contains world state, agents, and tick logic.
- `latticeville/render/` contains terminal rendering only.
- The renderer accepts state and returns output; no mutation.
- `latticeville/db/` optionally holds persistence for memories and replay logs.
- `latticeville/llm/` holds local LLM adapters and prompt helpers.

## World Model (tree)

- World is a tree of areas and objects (root = world, areas can contain subareas or objects, objects are leaves).
- Example: World → House (area) → Kitchen (subarea) → Stove (object).
- Each node has: `id`, `name`, `type` (`area`, `object`, `agent`), `parent_id`,
  and ordered `children`.
- Agents live in the tree as nodes with a current location (parent).
- Each agent maintains a **personal subtree / belief view** for locations and objects it knows.
- Agent belief views may diverge temporarily from the canonical world state (stale/partial),
  but follow the same structural schema (tree of nodes + containment).
- Perception uses the current area node and its immediate children.
- State transitions are deterministic given actions (non-determinism comes from LLM action generation).

## Core Agent Loop (per tick)

1. **Perceive** local environment (nearby objects + agents within visual range).
2. **Record observations** into memory stream:
   - Agent's own actions (what the agent did)
   - Other agents' actions (behaviors observed from nearby agents)
   - Object state changes (e.g., "refrigerator is empty", "stove is burning")
   - Inter-agent interactions (conversations, encounters)
3. **Retrieve** relevant memories using a scored subset.
4. **Decide** whether to react or follow current plan.
5. **Act** (single action description, which may include dialogue/utterances, + optional location change).
6. **Write back** action and any reflections/plans into memory.

### Tick-Based State Consistency

- Agents perceive state only as it existed at the end of the previous tick.
- All agent updates within a tick see the same world state snapshot (from the end of the previous tick).
- All state updates are applied at the end of the tick. The order in which agents are processed within a tick does not affect what state other agents observe.

### Object State Changes

- When an agent acts on an object, the LLM determines what state change should occur (e.g., action "making espresso" → coffee machine state changes from "off" to "brewing coffee").
- The canonical world state is updated with the new object state.
- Agents perceive updated object states in the next tick (step 1 of the loop).

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

Observations are direct perceptions recorded each tick. Agents perceive their local environment based on visual range: they observe all agents and objects within their current area (and immediate subareas).

- **Agent's own actions**: "Isabella Rodriguez is setting out the pastries"
  - Recorded in third person after the agent performs an action (from step 5 of the loop).
- **Other agents' actions**: "Maria Lopez is studying for a Chemistry test while drinking coffee"
  - Only agents within visual range (same area) are observed. Each agent sees what other agents in their area are doing.
- **Object states**: "The refrigerator is empty", "The stove is burning"
  - Objects in the agent's current area and immediate subareas are perceived.
- **Inter-agent interactions**: "Isabella Rodriguez and Maria Lopez are conversing about planning a Valentine's day party"
  - When agents engage in dialogue, both participants (and any observers in the same area) record the conversation as an observation.
  - Dialogue initiation is perceived: "John is initiating a conversation with Eddy"
  - Full conversation exchanges are recorded as they occur, allowing agents to remember what was said.

Agents only perceive what exists in their current location—they cannot observe agents or objects in other areas unless they move there.

### Location notes / annotations

- Agents can attach lightweight _annotations_ to locations (e.g., "The cafe is usually crowded").
- These can be modeled as memories with `type=annotation` (or a dedicated table/stream),
  typically with a `location_id`.

### Retrieval Scoring

Score = recency + relevance + importance, normalized to [0, 1].

- **Recency** decays exponentially since last access.
- **Relevance** can start as simple keyword overlap, or a simple BM25 implementation.
- **Importance** assigned at creation time by asking the LLM.

Select top-k memories that fit the context window.

## Reflection

- Check at the end of each agent tick: if the sum of importance scores for recent memories (since the last reflection) exceeds a threshold, trigger reflection.
- Generate 3-5 insights and store as reflections.
- Link reflections to supporting memories.

## Planning

- Agents create a daily plan in broad strokes (5–8 chunks), then recursively decompose it: day plan → hour chunks → 5–15 minute actions.
- Plans are stored in the memory stream with time and location, and are included in retrieval.
- When new observations occur, the agent decides whether to react; if so, it updates the plan from that point forward.

## LLM Usage (local only)

- Use [Qwen3](https://github.com/QwenLM/Qwen3) model via the [vLLM Metal](https://github.com/vllm-project/vllm-metal), with my own shallow adapter.
- Prompts should be short and deterministic where possible.
- Avoid external APIs.
- Batch multiple requests wherever possible (see [vLLM docs](https://docs.vllm.ai/en/latest/)). This requires experimentation but we are likely going to process multiple agents at the same time.

## Movement and Location Changes

- When an agent decides to move (step 5 of the agent loop), it specifies a destination location (area or object).
- Each location-to-location edge in the world tree has a fixed tick cost (`travel_ticks`). Total travel time is calculated by summing these costs along the path from current location to destination (graph-based distance, not geometric pathfinding). During travel, the agent is **in transit** and cannot interact or converse (prevents “talking before arrival”).
- While in transit, the agent is not considered present in any area for perception/visibility purposes.
- When `travel_ticks` reaches 0, the agent arrives: update `current_location` at the end of that tick and emit `MOVE(agent_id, from_location, to_location)`.
- Note: this diverges from the paper, which computes walking paths in a rendered environment/game engine ([paper](https://arxiv.org/pdf/2304.03442)); we use graph-based distance calculation with fixed tick costs per edge instead.

## Rendering (terminal)

- Multiple viewers can be attachable (e.g., one prints summary, one logs JSON, one draws ASCII).
- Viewers are tick-synchronized: they see whole-tick snapshots/events only (no partial updates).
- Any future simulator inputs (pause/step/commands) must enter as explicit simulator inputs,
  applied only at tick boundaries.
- Replay is event-sourced with periodic snapshots (see [Architecture](thinking/architecture.md)).
- A simple state debugger can be rendered as a separate viewer.

# References

- Paper Summary: [/thinking/paper/summary.md](/thinking/paper/summary.md)
- Paper Abstract: https://arxiv.org/abs/2304.03442
- Paper PDF: https://arxiv.org/pdf/2304.03442
