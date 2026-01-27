# Latticeville - Project + Technical Spec

# Summary

Latticeville is a local-only, terminal-UI simulation of a tiny cyberpunk neon village with LLM-driven characters. The main goal is to implement the core _memory-first_ loop from the Generative Agents paper using a fully local LLM system.

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
- Include replay support.

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
- Agents live in the tree as leaf nodes with a current location (parent).
- Each agent maintains a **personal subtree / belief view** for locations and objects it knows.
- Agent belief views may diverge temporarily from the canonical world state (stale/partial), but follow the same structural schema (tree of nodes + containment).
- Perception uses the current area node and the **object leaf nodes** contained in that area.
- State transitions are deterministic given actions and the same initial state (non-determinism comes from LLM action generation).
  - Deterministic does **not** imply “physically accurate” under conflicting same-tick actions; it only implies reproducible outcomes.

## Core Agent Loop (per tick)

1. **Perceive** local environment (nearby objects + agents within visual range).
2. **Record observations** into memory stream:
   - Agent's own actions (what the agent did)
   - Other agents' actions (behaviors observed from nearby agents), from the previous tick
   - Object state changes (e.g., "refrigerator is empty", "stove is burning")
   - Inter-agent interactions (conversations, encounters)
3. **Retrieve** relevant memories using a scored subset (includes observations, plans, and reflections).
4. **Plan** (if needed):
   - If no plan exists, create a daily plan in broad strokes (5–8 chunks).
   - Recursively decompose plans: day plan → hour chunks → 5–15 minute actions as needed.
   - Plans include time and location, stored in memory stream.
5. **Decide** whether to react to new observations or follow current plan.
   - If reacting, update the plan from that point forward.
6. **Act** (structured action selection).
   - The LLM selects **exactly one** action via tool/function calling.
   - Action is chosen from the current plan but returned in a machine-executable form.
   - The Agent always has to perform an action per tick, but the action can be `IDLE`
   - Invalid actions are handled by server-side validation and fall back to `IDLE`.
7. **Execute** the action deterministically in the simulator.
   - Simulator applies canonical state updates and emits structured events (see below).
8. **Write back** action (as natural language) and any reflections/plans into memory.
   - Memory narration is generated from templates based on the executed action/event, to keep
     memory consistent with canonical state and replay.

### Action selection via tool calling

2. **`act`** (decision making): Must be called exactly once per tick to select the agent's action.

#### Act tool

- **Tool name**: `act`
- **Guarantee**: model must call the tool once per tick (we include `IDLE` as a valid choice)
- **Output shape**: one of a small set of `kind` values, with arguments.

Conceptual schema:

```json
{
  "kind": "IDLE" | "MOVE" | "INTERACT" | "SAY",
  "move": { "to_location_id": "..." },
  "interact": { "object_id": "...", "verb": "USE" | "OPEN" | "CLOSE" | "TAKE" | "DROP" },
  "say": { "to_agent_id": "...", "utterance": "..." }
}
```

The simulator provides a per-tick list of valid targets:

- **Locations**: reachable _area/location_ ids for `MOVE` (not objects).
- **Objects**: object ids in the agent’s current area for `INTERACT` and `query`.
- **Agents**: agent ids in the current area for `SAY`.

The executor validates arguments against these sets and uses `IDLE` on invalid input.

### Tick-Based State Consistency

- Agents perceive state only as it existed at the end of the previous tick.
- All agent updates within a tick see the same world state snapshot (from the end of the previous tick).
- All state updates are applied at the end of the tick. The order in which agents are processed within a tick does not affect what state other agents observe.

### Object State Changes

- When an agent acts on an object, the chosen action includes the target object and an interaction verb.
- The simulator applies a deterministic transition (object-specific rule/state machine) to update
  canonical state.
- The simulator emits an `OBJECT_STATE_CHANGED(...)` event describing the transition.
- The state change can fail, for example when taking an item from an empty fridge, and this will be informed to the model and registered in the memory as attempted.
- Other agents perceive updated object states in the next tick (step 1 of the loop).
- The acting agent is aware of its own action immediately (and writes it to memory), even though
  environment perception remains tick-boundary consistent.

**Note:** The current design can lead to a race condition, whereby two agents interact with the same object, in the same tick, in a way that would be invalid.
For example, if there is a single item on the fridge, but two agents take a single item each.
We are going to **ignore this problem and allow the simulation to continue**, with an empty fridge in the example above.
This preserves determinism (same inputs → same results), but can yield an inaccurate/implausible outcome (e.g., “two successful takes from one item”).

## Memory Stream

Each memory record is an append-only entry with:

- `description` (text)
- `created_at` (tick)
- `last_accessed_at` (tick)
- `importance` (1–10)
- `type` (`observation`, `plan`, `reflection`, `action`)
- `links` to supporting records (for reflections)

### What gets recorded as observations

Observations are direct perceptions recorded each tick. Agents perceive their local environment based on visual range: they observe the other agents in their current area, and the objects (leaf nodes) in their current area.

- **Agent's own actions**: "Isabella Rodriguez is setting out the pastries"
  - Recorded in third person after the agent performs an action (from step 5 of the loop).
- **Other agents' actions**: "Maria Lopez is studying for a Chemistry test while drinking coffee"
  - Only agents within visual range (same area) are observed. Each agent sees what other agents in their area are doing.
- **Object states**: "The refrigerator is empty", "The stove is burning"
  - Objects in the agent's current area are perceived.
- **Inter-agent interactions**: "Isabella Rodriguez and Maria Lopez are conversing about planning a Valentine's day party"
  - When agents engage in dialogue, both participants (and any observers in the same area) record the conversation as an observation.
  - Dialogue initiation is perceived: "John is initiating a conversation with Eddy".
  - Conversation can only happen for agents in the same location.
  - Conversation proceeds at **one turn per tick** per speaking agent (i.e., one `SAY` action per tick).

Agents only perceive what exists in their current location. They cannot observe agents or objects in other areas unless they move there.

### Retrieval Scoring

We use min–max normalization per retrieval call, then sum the components:

- Compute raw component scores for each candidate memory \(m\): `recency_raw(m)`, `relevance_raw(m)`, `importance_raw(m)`.
- Min–max normalize each component across all candidates in the stream for that call:
  - `norm(x) = (x - min_x) / (max_x - min_x)`; if `max_x == min_x`, treat `norm(x) = 0`.
- Final score (equal weights by default):
  - `score(m) = recency_norm(m) + relevance_norm(m) + importance_norm(m)`

- **Recency** decays exponentially since last access.
- **Relevance** uses BM25 over the memory `description` field.
- **Importance** assigned at creation time by asking the LLM.

Select top-k memories that fit the context window. `k` should be configurable.

#### Importance Scoring

Importance is computed for all memory types (`observation`, `plan`, `reflection`, `action`) at creation time by asking the LLM to rate the memory's significance.

- **Prompt**: The LLM is asked to rate how impactful or significant the memory is for the agent's future decision-making and behavior, on a scale of 1–10.
- **Criteria**: Higher scores indicate memories that are likely to influence future actions, relationships, or plans (e.g., meeting someone new, completing a goal, learning something important). Lower scores indicate routine or mundane observations.
- **Normalization**: The 1–10 scale is normalized to [0, 1] for retrieval scoring using: `normalized_importance = (importance - 1) / 9`
- **Timing**: Importance is computed immediately after creating each memory, before it's added to the memory stream.

## Reflection

- Check at the end of each agent tick: if the sum of importance scores for recent memories (since the last reflection, inclusive) exceeds a threshold, trigger reflection.
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

- When an agent decides to move (step 5/6 of the agent loop), it specifies a destination **location/area** id in the `MOVE` action.
- Travel time is computed as: number of edges along the path \(\times\) a constant per-edge cost.
  - All edges have the same cost, set to `1`. This should be configurable.
- While in transit, the agent advances one edge per tick, occupying intermediate locations for perception/visibility so agents can perceive each other “on the way” and potentially re-plan.
- When the traversal completes, update `current_location` at the end of that tick and emit
  `MOVE(agent_id, from_location, to_location)`.

**Note:** this diverges from the paper, which computes walking paths in a rendered environment/game engine ([paper](https://arxiv.org/pdf/2304.03442)); we use graph-based distance calculation with fixed tick costs per edge instead.

## World transition model (ambient events)

In addition to agent actions, the simulator may apply world-level transitions each tick (e.g., time-of-day,
weather, ambient object changes). These are deterministic given the run seed/config and are emitted as
events (e.g., `WEATHER_CHANGED`, `TIME_ADVANCED`). Agents perceive these changes in the next tick.

This is a separate “world dynamics” step:

- **Weather system**: e.g., `weather_state` transitions (`CLEAR` → `RAIN` → `CLEAR`), wind, temperature
  bands. Emits `WEATHER_CHANGED(old, new)`.

The world model should remain simulator-owned (not agent-owned): it updates canonical state and emits events,
and agents can only react by perceiving the resulting state/event stream in subsequent ticks.

## Rendering (terminal)

- Multiple viewers can be attachable (e.g., one prints summary, one logs JSON, one draws ASCII).
- Viewers are tick-synchronized: they see whole-tick state (and optional events) only (no partial updates).
- Any future simulator inputs (pause/step/commands) must enter as explicit simulator inputs,
  applied only at tick boundaries.
- Replay/logging may store full per-tick state frames (simplest) or events with occasional state (more compact)
  (see [Architecture](thinking/architecture.md)).
- A simple state debugger can be rendered as a separate viewer.

## Tick time model

- Each tick represents a fixed unit of simulated time.
- The tick duration is a configurable constant (see `thinking/architecture.md` for configuration notes).

# References

- Paper Summary: [/thinking/paper/summary.md](/thinking/paper/summary.md)
- Paper Abstract: https://arxiv.org/abs/2304.03442
- Paper PDF: https://arxiv.org/pdf/2304.03442
