# Repository Guidelines

Guidelines for AI coding agents working on Latticeville. This file complements README.md with technical conventions, patterns, and restrictions.

## Project Overview

Latticeville is a local-only simulation for studying multi-agent systems with memory. It implements a memory-first agent loop (perceive → remember → retrieve → act) inspired by the Generative Agents paper. The architecture separates simulation logic from rendering for testability.

## Technology Stack

- **Language:** Python 3.12+
- **Package Manager:** `uv` (modern Python package manager)
- **Rendering:** Rich (terminal UI library)
- **Persistence:** JSONL run logs (file-based)
- **LLM Backends:** Local adapters (Ollama, MLX, vLLM) via environment configuration
- **Testing:** pytest
- **Linting/Formatting:** ruff

## Environment & Setup

**Prerequisites:**

- Python 3.12.9 (see `.python-version`)
- `uv` package manager installed

**Setup:**

```bash
uv sync                    # Install dependencies
uv run python -m latticeville  # Run simulation
```

**Environment Variables:**

- `OLLAMA_HOST` - Optional, defaults to localhost for Ollama LLM backend
- LLM backends configured via environment variables (no credentials in repo)

## Project Structure & Module Organization

```
latticeville/
├── latticeville/          # Core package
│   ├── __init__.py
│   ├── __main__.py        # Entry point: `python -m latticeville`
│   ├── app.py             # Application entry and main loop
│   ├── sim/               # Simulation core (world model, agents, tick logic)
│   ├── render/            # Terminal rendering (Rich, ASCII views)
│   ├── db/                # Persistence helpers (memories, replay logs)
│   └── llm/               # Local LLM adapters (Ollama, MLX, vLLM)
├── tests/                 # Automated tests (pytest)
├── data/                  # Local run logs and state (gitignored)
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
- `latticeville/db/` - Persistence helpers for memory streams and replay logs
- `latticeville/llm/` - Local LLM adapters and prompt helpers (Ollama, MLX, vLLM)

## Build & Test Commands

**Dependency Management:**

- Use `uv` for all package operations: `uv sync`, `uv add <package>`
- Add dev dependencies to `[dependency-groups.dev]` in `pyproject.toml`

**Running:**

- `uv run python -m latticeville` - Run the simulation loop
- `uv run pytest` - Run all tests
- `uv run pytest tests/path/to/test_file.py` - Run specific test file

**Code Quality:**

- `uv run ruff check .` - Lint code
- `uv run ruff format .` - Format code
- Both must pass before committing

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

- Use `pytest` with tests in `tests/` and names like `test_*.py`.
- This is an experimental project, so focus on validation of output and states rather than extensive test coverage.
- Prioritize proving the system works as expected (e.g., agent behavior matches paper concepts).
- Reference the [Generative Agents paper](https://arxiv.org/abs/2304.03442) when validating behavior, but this isn't a research project; practical validation over scientific rigor.
- Focus on deterministic unit tests for the discrete step engine and world model.
- For rendering, include snapshot-style tests using ASCII fixtures when possible.

## Local AI & Data Configuration

- This project is local-only. Do not add networked dependencies or telemetry.
- Configure LLM backends via environment variables (e.g., `OLLAMA_HOST`) and keep
  credentials out of the repo.
- Store run logs and local state in `data/` (gitignored).

## Commit & Pull Request Guidelines

**Commit Messages:**

- Short, sentence-case summaries (e.g., "Fix capitalization in project title")
- One logical change per commit
- Focused and descriptive

**Pull Requests:**

- Include short summary and rationale
- For UI changes, include example CLI output
- All tests and lint checks must pass
- Keep PRs focused on a single feature or fix
- This is a personal project open to the public; no formal review process required

## Security & Permissions

**AI Agents May:**

- Read any file in the repository
- Create/edit code files following conventions
- Run linting and formatting tools
- Run tests locally
- Add dependencies via `uv add` (but prefer asking for review)

**AI Agents Must Request Approval For:**

- Changing project metadata (`pyproject.toml` version, dependencies)
- Modifying `.gitignore` or repository structure
- Adding external API calls or networked dependencies
- Changing core architecture decisions
- Committing directly to main branch (use PRs)

**Never:**

- Commit secrets, API keys, or credentials
- Add telemetry or external tracking
- Break the local-only principle

## Good & Bad Examples

**✅ Good Patterns:**

- Stateless renderers that accept world state
- Deterministic simulation logic (testable)
- Type hints on public APIs
- Explicit file names: `time_step.py`, `world_state.py`

**❌ Avoid:**

- Tight coupling between sim and render modules
- Stateful renderers that mutate world state
- Networked dependencies or external APIs
- Vague naming or abbreviations

_Note: As the codebase grows, add specific file examples here._

## Edge Cases & Gotchas

- **Run logs:** Stored in `data/` directory (gitignored). Ensure the directory is writable before starting a run.
- **LLM Configuration:** All LLM backends configured via environment variables. No hardcoded endpoints.
- **Rendering:** Keep renderer interfaces narrow; the sim engine must remain UI-agnostic.
- **Memory Stream:** Append-only design. Retrieval uses scoring (recency + relevance + importance).

## When Stuck / Escalation

- **Ambiguous requirements:** Ask clarifying questions before implementing
- **Architecture decisions:** Propose plan and request review
- **Breaking changes:** Discuss impact and get approval
- **Unclear patterns:** Reference `thinking/spec.md` for design intent
