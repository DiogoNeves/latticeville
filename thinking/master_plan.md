# Master plan

This plan is optimized for **early end-to-end validation**: each phase is a “thin slice” that keeps components minimal but proves the interfaces end-to-end.

**Important**: This is a **living document**. If you get stuck on a phase or find that the plan doesn’t match reality, **re-evaluate and adjust**. Getting stuck is a signal that the plan needs updating—don’t force-fit implementation to match an outdated plan.

## Working with AI (recommended workflow)

Keep the feedback loop tight and the diffs small:

- **Small diffs**: prefer changes you can review in <10 minutes; avoid “big bang” refactors.
- **Acceptance criteria first**: before implementing, write down what “done” means (commands that pass + observable output).
- **Tiny eval loop** (run constantly):

```bash
uv run ruff format .
uv run ruff check .
uv run pytest
```

- **Use fakes to stay deterministic**: default to `FakeLLM` / fake embedder in tests, then swap in real backends behind the same interface.
- **Contracts over cleverness**: when uncertain, add a schema/validator + a test rather than expanding behavior.

## What’s already decided (current contracts)

These decisions are now encoded in `thinking/spec.md` and `thinking/architecture.md` and should be treated as the baseline:

- **Determinism + tick boundaries**:
  - Agents perceive world state as it existed **at the end of the previous tick**.
  - Canonical state updates are applied **at the end of the tick**.
  - “Deterministic” means reproducible outcomes, not necessarily physically accurate outcomes under conflicts.
- **Same-tick conflicts are tolerated**: if two agents perform conflicting object interactions in the same tick, the sim continues deterministically even if the outcome is implausible.
- **Action model (LLM tool calling)**:
  - Exactly **one** structured action per agent per tick.
  - `IDLE` is always allowed; invalid actions/args fall back to `IDLE`.
  - Action kinds: `IDLE` | `MOVE` | `INTERACT` | `SAY`.
- **Movement semantics**:
  - Movement is graph traversal with fixed per-edge tick cost (baseline 1 tick/edge).
  - While in transit, agents **occupy intermediate locations** for perception/visibility and can re-plan “on the way”.
- **Memory retrieval scoring**:
  - Retrieval uses a natural-language “query memory” (current observations + current plan step/goal).
  - Relevance is **embedding cosine similarity**; score uses per-call min–max normalization of recency/relevance/importance.
- **Sim → viewer contract**:
  - Viewers receive whole-tick payloads only (no partial state).
  - Viewers may drop intermediate ticks and render only the latest completed tick (**latest-frame semantics**).
- **Local LLM backend direction**:
  - Primary backend target: **Qwen3 via vLLM Metal**, behind a shallow adapter.
  - Batch agent requests where possible (implementation detail to be proven).

## Phase 0: Lock the contracts into code (schemas + stubs)

- Define the **core data structures** in code (shape-first):
  - canonical world tree (areas/objects/agents)
  - per-agent belief tree (same schema, partial/stale allowed)
  - `TickPayload` for viewers: `{ tick, state, events? }`
  - `Action` schema + validation + `IDLE` fallback
- Add minimal module scaffolding aligned to the architecture doc:
  - `latticeville/sim/`, `latticeville/render/`, `latticeville/db/`, `latticeville/llm/`
- Add **contract tests** for the schemas/validators (no simulation behavior yet).

Status: **complete**
Notes:

- Implemented Pydantic contracts (`latticeville/sim/contracts.py`) and exports.
- Added contract tests (`tests/test_contracts.py`) and a pytest path helper (`tests/conftest.py`).

Exit criteria:

- The codebase has importable types + validation stubs that match the docs (even if behavior is fake).

Acceptance checklist:

- `uv run ruff check .` passes
- `uv run pytest` passes (schema/validator contract tests)

## Phase 1: Minimal simulator loop (no LLM, deterministic)

- Implement a basic tick loop that:
  - advances time
  - runs world dynamics (optional but deterministic)
  - runs agent updates from a fixed snapshot (end-of-previous-tick)
  - applies all state updates at tick end
  - emits `TickPayload` per tick (state + optional events)
- Implement deterministic movement on a tiny graph:
  - multi-tick travel
  - intermediate occupancy for perception/visibility

Status: **complete**
Notes:

- Added minimal world state, movement traversal, patrol policy, and tick loop modules.
- Wired app to run a short loop and print tick summaries.
- Added deterministic tick loop tests.

Exit criteria:

- Running the app produces a changing world over ticks and emits stable tick payloads.

Acceptance checklist:

- `uv run pytest` includes deterministic tick-loop tests (fixed seed/config)
- A short run prints/emits multiple ticks and shows movement over time

## Phase 2: Terminal debug viewer (minimal but stable)

- Implement a terminal viewer that renders from `TickPayload`:
  - current tick
  - agent locations (including “in transit” / current node)
  - last \(k\) events (optional)
  - compact view of one agent’s belief or memory summary (optional)
- Ensure viewer obeys:
  - tick boundary rendering only
  - latest-frame semantics (can skip ticks)

Status: **complete**
Notes:

- Added JSONL replay log + separate Rich viewer that tails the log.
- Viewer renders tick, locations, recent events, and belief summary.
- Added snapshot-style viewer tests and live tailer with latest-frame semantics.

Exit criteria:

- Viewer consumes tick payloads and renders stable output across runs.

Acceptance checklist:

- Viewer renders from a saved `TickPayload` fixture (snapshot-style test or golden text)
- Viewer can skip ticks and still render the latest completed tick correctly

## Phase 3: Replay logging (JSONL) + deterministic replay

- Persist a run log (baseline: JSONL tick frames; optionally include events).
  - Include a `schema_version` field in replay records (and/or an initial run header record) so logs remain parseable as schemas evolve.
- Implement replay mode that:
  - reads the log
  - replays tick payloads through the same viewer pipeline

Exit criteria:

- A run can be replayed from disk and reproduces the same viewer outputs.

Acceptance checklist:

- A recorded run (JSONL) can be replayed and matches a baseline output (golden file or snapshot)

## Phase 4: LLM integration (FakeLLM first, then vLLM Metal)

- Add a deterministic `FakeLLM` that outputs structured actions for tests/demos.
- Add a shallow adapter for the real local backend:
  - target: Qwen3 via vLLM Metal
  - enforce “one tool call per tick” and `IDLE` fallback
- (If feasible) batch multiple agent requests per tick.
- See [LLM smoke test](thinking/vllm_metal_smoke.md)

Exit criteria:

- Swap between `FakeLLM` and the real adapter via configuration.

Acceptance checklist:

- With `FakeLLM`, tests are deterministic and cover action selection + validation + `IDLE` fallback
- With real backend configured, a short run completes without violating “one action per tick”

## Phase 5: Memory stream + retrieval (embedding-based)

- Implement append-only memory stream:
  - record observations/actions/plans/reflections as `description` + metadata
  - compute importance (LLM-rated 1–10, normalized for scoring)
- Implement retrieval:
  - create query memory text from the current situation
  - compute relevance via **embedding cosine similarity**
  - implement min–max normalization per retrieval call and top-k selection
- Provide a deterministic “fake embedder” for tests; wire a real local embedder later.

Exit criteria:

- Agent behavior measurably incorporates retrieved memories (and is testable with fake components).

Acceptance checklist:

- Retrieval has unit tests for: scoring components, per-call min–max normalization edge cases, top-k selection
- With fake embedder, retrieval returns expected memories deterministically

## Phase 6: Planning + reflection (paper-inspired, incremental)

- Planning:
  - daily plan in broad strokes (5–8 chunks)
  - recursive decomposition to hour chunks and 5–15 minute actions
  - re-plan from current point when reacting
- Reflection:
  - trigger when cumulative importance since last reflection exceeds threshold
  - generate 3–5 insights and link to supporting memories

Exit criteria:

- Reflections and plans appear occasionally and influence subsequent behavior in visible ways.

Acceptance checklist:

- Planning produces 5–8 chunk day plans and decomposes to finer steps (unit-tested)
- Reflection triggers on threshold and creates linked reflections (unit-tested)

## Phase 7: Re-plan (once the thin slice is fun)

- Reassess priorities based on what’s useful/fun:
  - richer viewer output (timelines, map, belief diffs)
  - improved retrieval performance (indexing, caching)
  - better reactions and social dynamics
  - belief divergence rules and debugging tools

Exit criteria:

- Updated plan with next milestones and any refactors based on real usage.
