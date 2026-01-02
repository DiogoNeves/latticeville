# Repository Guidelines

## Project Structure & Module Organization

- Use a `src/` layout for the Python app, e.g. `src/latticeville/`.
- Keep the simulation core separate from rendering so the loop stays testable:
  - `src/latticeville/sim/` for the world model and discrete time-step logic
  - `src/latticeville/render/` for Textual/Rich views and ASCII art rendering
  - `src/latticeville/db/` for SQLite access and persistence
  - `src/latticeville/llm/` for local LLM adapters (Ollama, MLX, vLLM)
- Suggested non-code directories:
  - `assets/` for ASCII templates, palettes, or map fixtures
  - `data/` for local SQLite files (gitignored)
  - `tests/` for automated tests

## Build, Test, and Development Commands

- Add a `pyproject.toml` and document the exact commands once set up.
- Example commands (replace with the real ones you add):
  - `python -m latticeville` - run the local simulation loop
  - `python -m pytest` - run tests
  - `python -m ruff check .` - lint (if configured)

## Coding Style & Naming Conventions

- Use 4-space indentation, type hints where practical, and docstrings for public APIs.
- Prefer explicit names: `time_step.py`, `world_state.py`, `ascii_renderer.py`.
- Keep renderer interfaces narrow so the sim engine is UI-agnostic.
- If a formatter/linter is added, run it on every change and note the command here.

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
