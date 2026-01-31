# Thinking docs index

This folder contains design and planning documents for Latticeville.

## How to read these docs

- **Start here:** [SPEC](/thinking/spec.md)
  - The **intended final outcome**: how the system should work when complete.
  - Not a build order.
- **Then:** [ARCHITECTURE](/thinking/architecture.md)
  - The key architectural decisions (and options we considered), with rationale.
  - This is where cross-cutting “contracts” live (tick semantics, sim→viewer payload, replay).
- **Finally (after baseline works):** [RESEARCH](/thinking/research.md)
  - Post-baseline experiment ideas and evaluation notes.
- **Paper grounding (reference only):** [PAPER SUMMARY](/thinking/paper/summary.md)
  - A summary of the _Generative Agents_ paper. It describes the paper, not this project.
- **Local LLM learnings:** [vLLM Metal: Direct offline API learnings](/thinking/vllm_metal_smoke.md)
  - What we learned about direct (no-server) LLM + embeddings APIs.

## Terminology (quick glossary)

- **Tick**
  - One discrete simulation step.
  - Represents a fixed amount of time (a configurable constant).
- **Canonical world state**
  - The simulator’s ground-truth world model.
- **Belief state**
  - Per-agent internal view of the world; may be partial or stale relative to the canonical world.
- **TickPayload**
  - The whole-tick data package emitted by the simulator at tick boundaries for viewers/logging/replay.
