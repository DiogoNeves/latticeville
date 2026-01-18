# Latticeville

A local-only simulation for studying multi-agent systems with memory. Implements a memory-first agent loop inspired by the Generative Agents paper, focusing on how agents perceive, remember, retrieve, and act in a small world.

**Status:** Early development — core simulation loop in progress.

## What It Does

Latticeville simulates LLM-driven characters in a tiny world with a focus on memory systems. Each agent follows a loop: perceive → remember → retrieve → act. The simulation runs entirely locally using terminal-based ASCII rendering.

## Quickstart

```bash
# Install dependencies
uv sync

# Run the simulation
uv run python -m latticeville
```

## Development

```bash
uv run pytest      # Run tests
uv run ruff check .  # Lint
uv run ruff format . # Format
```

## License

Open source — see [LICENSE](LICENSE) file.
