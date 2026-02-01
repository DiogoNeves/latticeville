# Architecture

This document explains how Latticeville works end-to-end. It is biased toward **testability**, **deterministic simulation**, and **replayability**, and it should remain consistent with `thinking/spec.md`.

## Goals and constraints

- **Local-only**: no external services, no telemetry.
- **Separation**: simulation core is UI-agnostic; viewers/renderers are stateless consumers.
- **Multiple viewers**: attach any number of viewers at once.
- **One-way data flow**: simulation emits data; viewers never mutate simulation state directly.
- **Tick synchronization**: viewers observe whole ticks only (no partial state).
- **Replayable**: record tick-based changes/events so runs can be replayed deterministically.

## Module boundaries (code layout)

- `latticeville/sim/`: world state, agents, tick logic (canonical truth).
- `latticeville/render/`: terminal rendering only (stateless; accepts state and returns output).
- `latticeville/db/`: persistence helpers (memories, run logs/replay).
- `latticeville/llm/`: local LLM adapters and prompt/tool helpers.

## World model: canonical world vs per-agent belief

See [`latticeville_data_models_diagram.png`](./latticeville_data_models_diagram.png) for a visual overview of the data models and state representations.

### Canonical world state

The simulation maintains a canonical **world tree** and a **grid map**:

- Root is “world”.
- **Areas** can contain objects.
- **Objects** are leaves.
- **Agents** live in the tree as leaf nodes (their parent is their current location).

Each node has: `id`, `name`, `type` (`area`, `object`, `agent`), `parent_id`, and ordered `children`.

The grid map is a single ASCII file for the entire world. Areas are defined by axis-aligned bounding boxes in `world.json`, and the tree is derived from those bounds. Agents move on the grid, and their current area is resolved from their grid position.

### Per-agent belief state

Each agent maintains a belief view using the **same tree schema**, but it may be **partial and/or stale** relative to the canonical world. This supports “I haven’t perceived the change yet” without inventing a second model.

#### Belief update rule (v0)

Belief is updated from perception via a **merge** into the agent’s belief tree:

- **Merge strategy**: merge newly perceived nodes into belief; if a node exists in both belief and perceived data (same `id`), the **perceived/canonical fields override** the belief fields for that node.
- **Scope**: the perceived slice is typically the agent’s current area and its immediate contents (objects + agents in that area).
- **Not globally synced**: belief outside the perceived slice remains as-is (and may be stale).

### Location annotations

We do not model a separate “annotation” concept. Subjective, place-related notes are ordinary observations recorded in the memory stream.

## Tick model and determinism

### Tick-based state consistency

To ensure deterministic behavior and consistent perception:

- **Agents perceive state only as it existed at the end of the previous tick**.
- **All agent updates within a tick see the same world snapshot** (end-of-previous-tick).
- **All state updates are applied at the end of the tick**.
- The order agents are processed within a tick must not change what other agents perceive.

### World dynamics

Separately from agent actions, the simulator can run a **WorldDynamics** step each tick that updates canonical world state and emits events (deterministic given seed/config), e.g.:

- `WEATHER_CHANGED(old, new)`
- `TIME_ADVANCED`

Agents can’t mutate WorldDynamics directly; they only react after perceiving resulting state/events on subsequent ticks.

## Agent loop (per tick)

The simulation follows a memory-first agent loop inspired by Generative Agents:

1. **Perceive** local environment (objects + agents in the current area).
2. **Record observations** into memory:
   - Own executed action (what the agent did)
   - Other agents’ actions observed from nearby agents (same area), from the previous tick
   - Object state changes
   - Inter-agent interactions (conversations, encounters)
3. **Retrieve** relevant memories (recency + relevance + importance).
4. **Plan** (if needed): daily plan in broad strokes (5–8 chunks), recursively decomposed into hour chunks and 5–15 minute actions.
5. **Decide** to react (re-plan) or follow current plan.
6. **Act**: choose **exactly one** structured action. `IDLE` is always allowed.
7. **Execute** deterministically in the simulator (canonical state update + event emission).
8. **Write back** action narration + any plans/reflections into memory.
   - Action narration is generated from templates derived from executed actions/events (no “free text → state” parsing).

## Memory system

### Memory stream records

Each memory record is append-only and includes:

- `description` (text)
- `created_at` (tick)
- `last_accessed_at` (tick)
- `importance` (1–10)
- `type` (`observation`, `plan`, `reflection`, `action`)
- `links` to supporting records (for reflections)

### Retrieval scoring

Retrieval ranks the memory stream against a natural-language “query memory” (current observations + current plan step/goal). For each memory \(m\), compute raw component scores, then min–max normalize per retrieval call and sum:

- `norm(x) = (x - min_x) / (max_x - min_x)`; if `max_x == min_x`, treat `norm(x) = 0`.
- `score(m) = recency_norm(m) + relevance_norm(m) + importance_norm(m)`

Notes:

- **Recency** decays exponentially since last access.
- **Relevance** uses embedding cosine similarity between query text and memory `description`.
- **Importance** is assigned at creation time by asking the LLM to rate 1–10, normalized to \([0, 1]\) via `normalized_importance = (importance - 1) / 9`.

Select top-k memories that fit the context window; `k` is configurable.

### Reflection trigger

At the end of each agent tick:

- If the sum of importance scores for recent memories (since the last reflection, inclusive) exceeds a threshold, trigger reflection.
- Generate 3–5 insights as reflection memories and link them to supporting memories.

## Action model (tool calling) and validation

The LLM acts as a decision policy: it selects **exactly one** structured action per tick, and the simulator is the only component that mutates canonical world state.

- **Guardrail**: the model must choose exactly one action via tool/function calling.
- **Fallback**: invalid action arguments are rejected by validation and replaced by `IDLE`.

Conceptual schema (mirrors `thinking/spec.md`):

```json
{
  "kind": "IDLE" | "MOVE" | "INTERACT" | "SAY",
  "move": { "to_location_id": "..." },
  "interact": { "object_id": "...", "verb": "USE" | "OPEN" | "CLOSE" | "TAKE" | "DROP" },
  "say": { "to_agent_id": "...", "utterance": "..." }
}
```

Per tick, the simulator provides valid targets:

- **Locations**: reachable area/location ids for `MOVE` (not objects).
- **Objects**: object ids in the agent’s current area for `INTERACT` (and any object queries).
- **Agents**: agent ids in the current area for `SAY`.

The executor validates arguments against these sets and uses `IDLE` on invalid input.

## Action execution semantics

### Movement and location changes

Movement uses **grid-based pathfinding (A*)** with fixed tick costs per step:

- Total travel time is calculated as: number of grid steps along the path \(\times\) a constant per-step cost.
- Baseline: **all steps have the same cost**, set to `1` tick per step.
- While in transit, the agent advances one grid step per tick, occupying intermediate positions for perception/visibility. This allows agents to perceive each other “on the way” and potentially re-plan.
- When traversal completes, update the agent’s location at the end of that tick and emit a `MOVE(agent_id, from_location, to_location)` event.

This aligns with the paper’s rendered/pathfinding approach, using discrete grid traversal.

### Object state changes

When an agent acts on an object:

- The LLM selects a structured `INTERACT` action (`object_id` + interaction verb).
- The simulator applies a deterministic object transition (object-specific rule/state machine).
- The simulator emits an `OBJECT_STATE_CHANGED(...)` event describing the transition.
- The state change can fail (e.g., taking an item from an empty fridge). Failures are surfaced to the agent and recorded as an attempted action.
- The canonical world state is updated with the new object state (or left unchanged on failure).
- The acting agent is aware of its own executed action immediately and writes it to memory.
- Other agents perceive updated object states on the next tick (tick boundary consistency).

#### Same-tick conflicts (explicitly tolerated)

The current design can yield implausible outcomes if two agents interact with the same object in the same tick (e.g., two successful “take” actions from one remaining item).

We **ignore this problem and allow the simulation to continue**. This preserves determinism even if some outcomes are physically inaccurate.

### Conversations

- Conversation can only happen for agents in the same location.
- Conversation proceeds at **one turn per tick** per speaking agent (one `SAY` action per tick).
- Participants (and observers in the same area) record the conversation as an observation.

## Sim → viewer contract

Define a single “whole tick” payload that viewers consume:

- **State**: the latest state needed to render/debug (canonical state + per-agent belief state).
- **Events (optional)**: a small list of semantic events that happened during the tick.
  - Events are convenient for debugging and compact logs, but normal rendering can ignore them and just render `state`.

Key properties:

- **Immutability**: treat tick payloads as read-only data.
- **Tick boundary**: a viewer receives payloads only after the simulator has fully applied the tick.
- **Latest-frame semantics**: viewers are allowed to skip intermediate ticks and render only the latest completed tick.

## Editor mode

A separate editor view renders the **entire world map** and does not run the simulation. It allows cursor navigation and definition of room bounding boxes directly on the grid, with on-screen shortcuts and resize-aware layout.

### TickPayload

- `tick`: integer tick id (monotonic within a run)
- `state`: **full snapshot** of state at end of tick (keep it simple; no diffing required)
- `events`: optional list of events that occurred during the tick

### Viewers: tick sync + buffering

Viewers must only render at tick boundaries; they should never observe partially-applied state.

- **Default viewer model (double-buffering)**:

  - `last_complete_tick`: the last fully-applied tick frame
  - `currently_updating_tick`: a staging slot while ingesting a new tick frame
  - render always uses `last_complete_tick`

- Dropping intermediate ticks is fine for most viewers (latest-frame semantics). In practice:
  - if multiple `TickPayload`s arrive between render steps, keep only the newest tick and discard older ones
  - render should always show the most recent **complete** tick payload available at that render step
- Debug viewers may retain the last \(k\) tick frames/events to render sequences or timelines.

The simulator should not retain per-viewer event buffers; it publishes `TickPayload`s, and each viewer decides how much history to keep.

## sim→viewer comms and replay

### Dataflow (high-level)

```mermaid
flowchart LR
  LLM[LLM / Handcrafted policy] --> SIM[Simulation tick]
  WORLD[WorldDynamics] --> SIM
  SIM -->|TickPayload (whole tick)| BUS[EventBus (in-process)]
  BUS --> V1[Viewer A (terminal)]
  BUS --> V2[Viewer B (logger/metrics)]
  SIM -->|Replay records (JSONL)| LOG[(Run log on disk)]
```

## Simulator inputs (one-way flow preserved)

If/when we need inputs (pause, step, commands), they should enter as an explicit **SimulatorInput** stream, consumed only at tick boundaries. Viewers can produce inputs, but the input path is a separate interface from the output path.

## Replay: storage and communication options

Below are options for how to connect simulator and viewers and how to store replay data. These can be mixed (e.g., in-process delivery + file logging).

### Option A: In-process pub/sub + JSONL replay log (baseline)

- Simulator calls subscribers each tick with `TickPayload(state, events)`.
- Simulator also appends replay records to an append-only JSONL file.

### Option B: Append-only event log as the “bus” (file tailing)

- Simulator writes an append-only JSONL log (one record per tick, plus optional periodic snapshots).
- Viewers tail the log file and render as new ticks appear.

### Option C: Queryable store for replay and memory

- Simulator writes tick rows and event rows to a queryable store (optionally snapshots).
- Viewers query “latest tick” and render, or follow a polling loop.

### Log format options

We use a **payload log** format:

1. **Payload log (simplest)**: store `TickPayload(state, events?)` per tick, where `state` is a full snapshot.

#### Schema versioning

Include a `schema_version` field in each replay record (and/or in an initial run header record) to detect mismatches as schemas evolve.

We make **no backwards-compatibility guarantees** for replay logs: readers/viewers are expected to match the log schema version they are consuming.

## LLM backend

The simulation uses local LLM backends exclusively (no external APIs):

- **Primary backend**: [Qwen3](https://github.com/QwenLM/Qwen3) model via [vLLM Metal](https://github.com/vllm-project/vllm-metal), with a shallow adapter in `latticeville/llm/`.
- **Batching**: Multiple agent requests are batched wherever possible (see [vLLM docs](https://docs.vllm.ai/en/latest/)). This requires experimentation but we are likely going to process multiple agents at the same time.
- **Prompts**: should be short and deterministic where possible.
- **Testing**: use a `FakeLLM` for deterministic tests and fixed seeds.
- **Direct offline API learnings**: see [vLLM Metal: Direct offline API learnings](/thinking/vllm_metal_smoke.md).

## Configuration (simulation constants)

Some core constants should be configurable without changing code. We will keep them in a small config file loaded at startup (format can be JSON/TOML/YAML; the exact choice can be made during implementation).

Baseline constants to include:

- `tick_duration`: the fixed amount of simulated time represented by one tick (e.g., 1 minute). This should be a single constant used consistently across planning, scheduling, and world dynamics.
- `travel_ticks_per_edge`: the time cost to traverse one edge in the world tree graph. Baseline value: `1`.

### Compaction / “forgetting” old events

If we want to “forget” older events for efficiency, we do it by **starting a new segment** that begins with a snapshot:

- `run-<id>/segment-000.jsonl` (starts with snapshot, then events)
- rotate every N ticks or bytes into `segment-001.jsonl` (starts with snapshot, then events)

Old segments can optionally be deleted or compressed. This avoids rewriting large files while keeping replay fast.
