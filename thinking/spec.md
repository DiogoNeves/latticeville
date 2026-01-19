# 🏘️ Latticeville — Project + Technical Spec

# Summary
Latticeville is a local-only, terminal-UI simulation of a tiny cyberpunk neon village with LLM-driven characters. The main goal is to implement the core *memory-first* loop from the Generative Agents paper using a fully local LLM system. 🧱🤖

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
- `latticeville/db/` optionally holds persistence for memories and replay logs (defer for v1).  
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
Observations are direct perceptions recorded each tick:  
- **Agent's own actions**: "Isabella Rodriguez is setting out the pastries"  
- **Other agents' actions**: "Maria Lopez is studying for a Chemistry test while drinking coffee"  
- **Object states**: "The refrigerator is empty", "The stove is burning"  
- **Inter-agent interactions**: "Isabella Rodriguez and Maria Lopez are conversing about planning a Valentine's day party"  

The agent's own action (from step 5 of the loop) is recorded as an observation in third person (e.g., "Isabella Rodriguez is setting out the pastries").

### Location notes / annotations
- Agents can attach lightweight *annotations* to locations (e.g., "The cafe is usually crowded").  
- These can be modeled as memories with `type=annotation` (or a dedicated table/stream),
  typically with a `location_id`.  

### Retrieval Scoring (minimal)
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

## Rendering (terminal)
- For v1, rendering is a debug view that outputs simulation state per tick (pretty later).
- Multiple viewers should be attachable (e.g., one prints summary, one logs JSON, one draws ASCII).
- Viewers are tick-synchronized: they see whole-tick snapshots/events only (no partial updates).
- Any future simulator inputs (pause/step/commands) must enter as explicit simulator inputs,
  applied only at tick boundaries.
- Replay is event-sourced with periodic snapshots (see [Architecture](thinking/architecture.md)).

# Questions / Open Decisions
- Should relevance use embeddings or simple keyword overlap for v1?
- Should reflections be included in the first milestone or deferred?
- What exactly goes into `TickPayload`: which parts of canonical state vs belief summaries?
- Should we standardize events early (e.g., `MOVE(agent_id, from, to)`) or keep free-text?

# References
- Paper Abstract: https://arxiv.org/abs/2304.03442
- Paper PDF: https://arxiv.org/pdf/2304.03442