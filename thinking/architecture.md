# Architecture decisions (draft)

This document records the current architectural decisions for Latticeville, plus the open questions we still need to answer. It is intentionally biased toward **early end-to-end validation** and **testability**.

## Goals and constraints

- **Local-only**: no external services, no telemetry.
- **Separation**: simulation core is UI-agnostic; viewers/renderers are stateless consumers.
- **Multiple viewers**: attach any number of viewers at once.
- **One-way data flow**: simulation emits data; viewers never mutate simulation state directly.
- **Tick synchronization**: viewers observe whole ticks only (no partial state).
- **Replayable**: record tick-based changes/events so we can replay runs deterministically.

## sim→viewer comms and replay

We will implement:

- **In-process pub/sub**: simulator publishes a whole-tick payload at tick boundaries.
- **Append-only JSONL run log**: simulator writes replay records to disk (events + periodic snapshots).

This yields fast iteration and keeps the schema stable while we discover what belongs in a tick.

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

### Agent LLM as a decision policy (baseline)

For determinism and replayability, treat the LLM as a **decision policy** that selects one structured action per tick.
The simulator is the only component that mutates canonical world state.

- **Guardrail**: the model must choose **exactly one** action via tool/function calling.
- **Fallback**: invalid action arguments are rejected by validation and replaced by `NOOP`/`WAIT`.
- **Narration**: action → memory is rendered from templates after execution (no free-text parsing).

### World dynamics (baseline-capable, grows over time)

Separately from agent decisions, the simulator runs a **WorldDynamics** step each tick that updates canonical
world state and emits events. This supports things like:

- **Weather**: `WEATHER_CHANGED`
- **Time**: `TIME_ADVANCED`
- **Village maintenance / services (future)**: repairs, outages, restocking, scheduled work (`MAINTENANCE_*`, `SERVICE_*`)

WorldDynamics should be deterministic given run seed/config (for replayability). Agents can’t mutate it directly;
they only react after perceiving the resulting state/events on subsequent ticks.

## Core model: canonical world vs per-agent belief

- **Canonical world state**: the simulation’s ground-truth world (tree of nodes: world → areas → objects; agents as nodes located in the tree).
- **Per-agent belief state**: each agent maintains its own internal representation of the world (same tree schema), which may be **partial or stale** relative to the canonical world.
  - This allows divergence (e.g., an agent hasn’t perceived a change yet) while keeping data structures consistent.

This aligns with the _Generative Agents_ world modeling approach (environment represented as a containment tree of locations/objects, converted to natural language for prompting) as summarized in [Summary](thinking/paper/summary.md) and described in the paper itself ([arXiv abstract](https://arxiv.org/abs/2304.03442)).

### Location annotations

Agents can attach lightweight **annotations** to locations in their belief trees (e.g., "The cafe is usually crowded"). These exist only in the agent's belief state, not in the canonical world, representing subjective observations about locations. These can be modeled as memories with `type=annotation` (or a dedicated table/stream), typically with a `location_id`.

## Tick-based state consistency

To ensure deterministic behavior and consistent perception:

- **Agents perceive state only as it existed at the end of the previous tick**.
- **All agent updates within a tick see the same world state snapshot** (from the end of the previous tick).
- **All state updates are applied at the end of the tick**. The order in which agents are processed within a tick does not affect what state other agents observe.

This guarantees that agents operating in parallel within a tick cannot observe each other's in-progress changes, maintaining consistency and determinism.

## Object state changes

When an agent acts on an object:

- The LLM selects a structured `INTERACT` action (`object_id` + interaction verb).
- The simulator applies a deterministic object transition (object-specific rule/state machine).
- The canonical world state is updated with the new object state.
- Agents perceive updated object states in the next tick (during the perception phase).

This separation ensures that state transitions are explicit and that perception always operates on stable, complete state snapshots.

## Movement and location changes

Movement uses a graph-based distance calculation with fixed tick costs per edge:

- Each location-to-location edge in the world tree has a fixed `travel_ticks` cost.
- Total travel time is calculated by summing these costs along the path from current location to destination (graph-based distance, not geometric pathfinding).
- During travel, the agent is **in transit** and cannot interact or converse (prevents "talking before arrival").
- While in transit, the agent is not considered present in any area for perception/visibility purposes.
- When `travel_ticks` reaches 0, the agent arrives: `current_location` is updated at the end of that tick and a `MOVE(agent_id, from_location, to_location)` event is emitted.

This diverges from the Generative Agents paper, which computes walking paths in a rendered environment/game engine; we use graph-based distance calculation with fixed tick costs per edge instead.

## Sim → viewer contract (recommended shape)

Define a single “whole tick” payload that viewers consume:

- **Snapshot**: the latest state needed to render/debug (canonical state + per-agent belief summaries).
- **Events**: a list of semantic events that happened during the tick.
  - **Agent action events** (canonical): `MOVE`, `INTERACT`, `SAY`, `WAIT/NOOP`, plus derived transitions like `OBJECT_STATE_CHANGED`.
  - **World events** (canonical): e.g., `WEATHER_CHANGED`, `TIME_ADVANCED`.
  - **Optional debug events** (non-canonical): e.g., reflection/plan summaries (these are also stored in agent memory streams).

Key properties:

- **Immutability**: treat tick payloads as read-only data.
- **Tick boundary**: a viewer receives payloads only after the simulator has fully applied the tick.
- **Backpressure**: viewers are allowed to skip intermediate ticks and render only the latest state (configurable per viewer).

### TickPayload (conceptual)

- `tick`: integer tick id (monotonic within a run)
- `snapshot`: optional snapshot of state at end of tick
  - emitted periodically (e.g., every 50 ticks), and also at tick 0/start
- `events`: list of events that occurred during the tick

### Why both snapshot + events?

- Snapshots make it easy to render/debug the _current truth_.
- Events make it easy to:
  - animate or interpret changes (e.g., viewer chooses how to visualize `MOVE`)
  - record compact replay logs
  - build audit trails and tests (“did we produce the expected event sequence?”)

### Viewers: tick sync + backpressure behavior

Viewers must only render at tick boundaries; they should never observe partially-applied state.

We will implement backpressure as **per-viewer “latest tick” queues**:

- Each viewer has a queue of size 1.
- Publishing a tick overwrites any unconsumed tick for that viewer.
- Effect: slow viewers drop intermediate ticks and always render the latest available completed tick.

This keeps the simulator unblocked while still allowing “render every tick” viewers if they can keep up.

## Simulator inputs (one-way flow preserved)

If/when we need inputs (pause, step, commands), they should enter as an explicit **SimulatorInput** stream, consumed only at tick boundaries. Viewers can _produce_ inputs, but the input path is a separate interface from the output path.

## Replay: storage and communication options

Below are options for how to connect simulator and viewers and how to store replay data. These can be mixed (e.g., in-process delivery + file logging).

### Option A — In-process pub/sub + JSONL replay log (recommended for v1)

**Design**

- Simulator calls subscribers each tick with `TickPayload(snapshot, events)`.
- Separately, simulator appends tick payloads (or just events + periodic snapshots) to a **JSON Lines** file (`.jsonl`) for replay.

**Pros**

- Very fast to implement; minimal moving parts.
- Multiple viewers are trivial (just multiple subscribers).
- Easy to test deterministically with a fake LLM and fixed seed.
- JSONL replay is human-inspectable, versionable, and easy to diff.

**Cons**

- Viewers must run in the same process (unless you add another transport later).
- Long runs can produce large logs unless you store only events + periodic snapshots.

**When to choose**

- Early development / E2E walking skeleton.

### Option B — Append-only event log as the “bus” (file tailing)

**Design**

- Simulator writes an append-only JSONL log (one record per tick, plus optional periodic snapshots).
- Viewers “tail” the log file and render as new ticks appear.

**Pros**

- Clean separation: viewers can run in separate processes.
- Replay is inherent (the log _is_ the run).
- Easy to attach new tools/viewers post-hoc.

**Cons**

- Need careful handling for atomic writes/flush per tick.
- Viewers need logic for partial reads and log rotation.
- Harder to do “request/response” style debugging (but still possible via separate input channel).

**When to choose**

- When you want multi-process viewers or long-lived “watchers” without embedding everything into one process.

### Option C — Queryable store for replay and memory (future)

**Design**

- Simulator writes tick rows and event rows to a queryable store (optionally snapshots).
- Viewers query “latest tick” and render, or follow a polling loop.

**Pros**

- Queryable timeline (“show last 50 moves”, “filter only agent X”, etc.).
- Random access and faster seeking for replay (especially with periodic snapshots).
- Can unify replay logging and memory persistence under one storage layer.

**Cons**

- Schema, migrations, and versioning complexity early.
- Multi-process concurrency and locking considerations.
- Overkill for the first E2E validation.

**When to choose**

- When you want richer analytics/debugging queries, or long-lived runs with offline analysis.

## Do we need a queryable store right now?

**For sim↔viewer communication and replay**: no. Option A (in-process + JSONL) is usually the fastest path to a robust E2E loop with replay.

**For memory persistence**: maybe later. A good pattern is:

- v1: in-memory memory store + deterministic tests + optional JSONL export
- v2+: evaluate a queryable store for long-lived runs, richer queries, and offline analysis

## LLM backend

The simulation uses local LLM backends exclusively (no external APIs):

- **Primary backend**: [Qwen3](https://github.com/QwenLM/Qwen3) model via [vLLM Metal](https://github.com/vllm-project/vllm-metal), with a shallow adapter in `latticeville/llm/`.
- **Batching**: Multiple agent requests are batched wherever possible (see [vLLM docs](https://docs.vllm.ai/en/latest/)). This requires experimentation but we are likely going to process multiple agents at the same time.
- **Prompts**: Should be short and deterministic where possible.
- **Testing**: Use a `FakeLLM` for deterministic tests and fixed seeds.

## Open questions (to answer as we build)

- **Tick payload schema**: how much canonical world state vs per-agent belief detail should be included each tick?
- **Action schema**: confirm the exact `act` schema (kinds + validation rules) and what we include as canonical events vs debug-only events.
- **Replay compatibility**: how do we version tick logs as schemas evolve?
- **Belief divergence**: what are the explicit rules for how and when belief state updates from perception?
- **Rendering cadence**: should viewers get every tick but be allowed to drop, or should the simulator emit every N ticks?

## Replay details (Option A implementation notes)

### Log format: event-sourced with periodic snapshots

We will write a run log as JSONL records. Conceptually:

- A **snapshot record** contains enough state to reconstruct the world/beliefs at a tick.
- An **event record** contains changes that occurred since the last snapshot.

New viewers (or a replay tool) can:

1. Load the latest snapshot.
2. Replay subsequent events to reach the current tick.

### Compaction / “forgetting” old events

If we want to “forget” older events for efficiency, we do it by **starting a new segment** that begins with a snapshot:

- `run-<id>/segment-000.jsonl` (starts with snapshot, then events)
- rotate every N ticks or bytes into `segment-001.jsonl` (starts with snapshot, then events)

Old segments can optionally be deleted or compressed. This avoids rewriting large files while keeping replay fast.
