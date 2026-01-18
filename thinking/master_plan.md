# Master plan (draft)

This plan is optimized for **early end-to-end validation**: each milestone is a “thin slice” that keeps components simple but proves the interfaces.

## Phase 0 — Agree on contracts (shape first)

- Define the **core data structures** (shape only):
  - canonical world state (location/object tree + agents)
  - per-agent belief state (same schema, partial/stale allowed)
  - tick payload for viewers (events every tick + periodic snapshots)
- Decide the initial **sim→viewer communication** approach (decision: in-process pub/sub + JSONL replay log).
- Decide snapshot cadence and log segmentation/rotation strategy.

Exit criteria:
- One document (and/or module stubs) describes the tick payload schema clearly.

## Phase 1 — Debug viewer (terminal, minimal)

- Implement a terminal debug viewer that prints:
  - current tick
  - agent locations
  - last N events
  - optionally a compact view of one agent’s belief state

Exit criteria:
- Viewer can consume a tick payload and render a stable textual output.

## Phase 2 — Simulator loop (no LLM)

- Implement a simple tick loop that:
  - advances time
  - applies deterministic, hardcoded state changes (including at least one movement event)
  - emits a tick payload each tick

Exit criteria:
- Running the app produces a sequence of ticks with events and changing state.

## Phase 3 — Wire simulator to viewer (chosen comms)

- Connect simulator output to one or more viewers.
- Ensure tick synchronization (no partial updates).
- Add replay logging (JSONL event log + periodic snapshots, segmented/rotated as needed).

Exit criteria:
- Can run a simulation and replay from the log to reproduce the same viewer outputs.

## Phase 4 — Add a local LLM adapter (minimal)

- Choose the simplest local backend to start (likely Ollama, unless vLLM is already set up locally).
- Add a **FakeLLM** first for deterministic tests, then the real adapter.
- Use the LLM only to select among a small set of actions (keep parsing simple).

Exit criteria:
- Swap between FakeLLM and real local LLM via configuration.

## Phase 5 — Implement memory + retrieval (v1)

- Append observations/actions to memory stream.
- Retrieval scoring starts minimal (keyword overlap + recency + importance heuristic).
- Persist memory in-memory initially; add optional persistence later.

Exit criteria:
- An agent’s action each tick incorporates retrieved memories in a measurable way.

## Phase 6 — Reflections + planning (incremental)

- Implement reflection triggers (importance threshold).
- Generate 1–3 insights with links to supporting memories.
- Introduce a minimal plan representation (single-step intentions first, expand later).

Exit criteria:
- Reflections appear occasionally and influence subsequent behavior.

## Phase 7 — Re-plan

- Reassess architecture and priorities based on what’s fun/useful:
  - richer viewer output
  - better retrieval (embeddings)
  - better plans/reactions
  - location annotations and belief divergence rules

Exit criteria:
- Updated plan with next milestones and any refactors.

