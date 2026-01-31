# Latticeville

A local-only simulation for studying multi-agent systems with memory. Implements a memory-first agent loop inspired by the [Generative Agents paper](https://arxiv.org/abs/2304.03442), focusing on how agents perceive, remember, retrieve, and act in a small world.

## Project approach (spec-first)

This project is being developed **spec-first**: I’m actively working on the written spec, and I’m treating it as the source of truth for how the system should behave when complete.

- **Everything should be clearly defined in text first**: interfaces, tick semantics, data shapes, and invariants.
- **Later:** I plan to treat **AI as a compiler**, taking those written contracts and “compiling” them into code changes (rather than letting code drift ahead of the spec).

## What It Does

Latticeville simulates LLM-driven characters in a tiny world with a focus on memory systems. Each agent follows a loop: perceive → remember → retrieve → act. The simulation runs entirely locally using terminal-based ASCII rendering.

In the baseline design, the LLM acts as a **decision policy**: each tick it selects exactly one structured action (e.g., MOVE/INTERACT/SAY/NOOP) via tool/function calling, and the simulator applies deterministic state transitions and logs events for replay.

The simulator also supports a separate **world dynamics** step (e.g., weather/time now; later, village maintenance/services) that updates canonical state and emits events agents can perceive.

## Documentation

- [Thinking docs index](thinking/index.md): Start here (reading order + glossary)
- [Technical Specification](thinking/spec.md): Final intended outcome (vision document)
- [Architecture](thinking/architecture.md): Key decisions and cross-cutting contracts

Quick excerpt from the index:

> Start here: `thinking/spec.md` (final intended outcome) → then `thinking/architecture.md` (contracts/rationale).

## Quickstart

```bash
# Install dependencies
uv sync

# Run the simulation
uv run python -m latticeville
```

## LLM Backends (local)

Default backend is `fake` (deterministic). To use the real MLX model:

```bash
# Real MLX LLM (downloads model on first run)
uv run python -m latticeville --llm mlx --model-id Qwen/Qwen3-4B-MLX-4bit
```

Environment alternatives:

```bash
LATTICEVILLE_LLM=mlx LATTICEVILLE_MODEL_ID=Qwen/Qwen3-4B-MLX-4bit \
  uv run python -m latticeville
```

## Development

```bash
uv run pytest      # Run tests
uv run ruff check .  # Lint
uv run ruff format . # Format
```

## License

Open source, see [LICENSE](LICENSE) file.
