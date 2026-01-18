# Repository Guidelines

## Project Structure & Module Organization

```
latticeville/
├── latticeville/          # Core package
│   ├── __init__.py
│   ├── __main__.py        # Entry point: `python -m latticeville`
│   ├── app.py             # Application entry and main loop
│   ├── sim/               # Simulation core (world model, agents, tick logic)
│   ├── render/            # Terminal rendering (Rich, ASCII views)
│   ├── db/                # SQLite persistence (memories, replay logs)
│   └── llm/               # Local LLM adapters (Ollama, MLX, vLLM)
├── tests/                 # Automated tests (pytest)
├── data/                  # Local SQLite files (gitignored)
├── assets/                # ASCII templates, palettes, map fixtures
├── thinking/              # Design docs and research notes
│   ├── spec.md            # Technical specification
│   └── paper/             # Paper summaries and references
├── pyproject.toml         # Project metadata and dependencies
└── README.md              # Project overview and quickstart
```

**Module Responsibilities:**
- `latticeville/sim/` - World model and discrete time-step logic (testable, UI-agnostic)
- `latticeville/render/` - Rich views and ASCII art rendering (stateless, accepts state)
- `latticeville/db/` - SQLite access and persistence for memory streams
- `latticeville/llm/` - Local LLM adapters and prompt helpers (Ollama, MLX, vLLM)

## Build, Test, and Development Commands

- Use `uv` for dependency management and tool execution (`uv sync`, `uv add`).
- Example commands:
  - `uv run python -m latticeville` - run the local simulation loop
  - `uv run pytest` - run tests
  - `uv run ruff check .` - lint
  - `uv run ruff format .` - format

## Coding Style & Naming Conventions

- Use 4-space indentation, type hints where practical, and docstrings for public APIs.
- Prefer explicit names: `time_step.py`, `world_state.py`, `ascii_renderer.py`.
- Keep renderer interfaces narrow so the sim engine is UI-agnostic.
- Run `ruff check` and `ruff format` on every change.

## CLI Rendering

- Use Rich for a simple, pane-based CLI (e.g., `Layout` + `Panel`) to show context
  alongside the simulation view.
- Keep rendering stateless: accept the world state and return ASCII/console output.

## Testing Guidelines

- Plan to use `pytest` with tests in `tests/` and names like `test_*.py`.
- Focus on deterministic unit tests for the discrete step engine and world model.
- For rendering, include snapshot-style tests using ASCII fixtures when possible.

## Local AI & Data Configuration

- This project is local-only. Do not add networked dependencies or telemetry.
- Configure LLM backends via environment variables (e.g., `OLLAMA_HOST`) and keep
  credentials out of the repo.
- Store SQLite data in `data/` (gitignored) and keep schema migrations tracked in
  code or `migrations/` if introduced.

## Commit & Pull Request Guidelines

- Existing commit messages are short, sentence-case summaries (e.g., "Fix capitalization in project title").
- Keep commits focused and descriptive; prefer one logical change per commit.
- For PRs, include a short summary, rationale, and example CLI output for UI changes.
