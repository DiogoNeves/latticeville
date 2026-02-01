"""Module entry point for `python -m latticeville`."""

from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from latticeville.app import run_simulation, run_simulation_with_viewer
from latticeville.db.replay_log import RUN_LOG_NAME
from latticeville.render.live_tail import tail_replay_log
from latticeville.render.replay_picker import pick_and_run_replay
from latticeville.render.replay_reader import read_tick_payloads
from latticeville.render.viewer import render_tick
from latticeville.render.world_editor import run_world_editor

DEFAULT_REPLAY_DIR = Path("replay")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Latticeville simulation.")
    parser.add_argument(
        "--view",
        action="store_true",
        help="Tail a replay log and render the live viewer.",
    )
    parser.add_argument(
        "--main-view",
        action="store_true",
        help="Run simulation and render the main world viewer.",
    )
    parser.add_argument(
        "--edit-world",
        action="store_true",
        help="Open the world map editor (no simulation).",
    )
    parser.add_argument(
        "--replay",
        type=Path,
        default=None,
        help="Replay a saved run folder through the viewer.",
    )
    parser.add_argument(
        "--replay-view",
        action="store_true",
        help="Select a replay run and view it in the main viewer.",
    )
    parser.add_argument(
        "--run-folder",
        type=Path,
        default=None,
        help="Run folder to view or replay (defaults to latest).",
    )
    parser.add_argument(
        "--replay-dir",
        type=Path,
        default=DEFAULT_REPLAY_DIR,
        help="Base replay directory for new runs.",
    )
    parser.add_argument(
        "--llm",
        default=None,
        help="LLM backend to use: prompt, fake, or mlx (simulation mode only).",
    )
    parser.add_argument(
        "--model-id",
        default=None,
        help="Model ID for mlx backend (simulation mode only).",
    )
    parser.add_argument(
        "--embedder",
        default=None,
        help="Embedder backend to use: fake or qwen (simulation mode only).",
    )
    parser.add_argument(
        "--embed-model-id",
        default=None,
        help="Model ID for qwen embedder (simulation mode only).",
    )
    parser.add_argument(
        "--ticks",
        type=int,
        default=None,
        help="Number of ticks to run (simulation mode only). Omit for infinite.",
    )
    args = parser.parse_args()

    if args.view:
        run_folder = args.run_folder or _latest_run_folder(args.replay_dir)
        if run_folder is None:
            raise SystemExit("No run folder found. Run a simulation first.")
        tail_replay_log(run_folder / RUN_LOG_NAME)
        return

    if args.replay_view:
        pick_and_run_replay(args.replay_dir)
        return

    if args.edit_world:
        run_world_editor(base_dir=Path("world"))
        return

    if args.main_view:
        created_run = run_simulation_with_viewer(
            args.replay_dir,
            ticks=args.ticks,
            llm_backend=args.llm,
            model_id=args.model_id,
            embedder_backend=args.embedder,
            embedder_model_id=args.embed_model_id,
        )
        print(f"Run saved to {created_run}")
        return

    if args.replay is not None:
        run_folder = args.replay
    else:
        run_folder = args.run_folder

    if run_folder:
        _replay_run(run_folder)
        return

    created_run = run_simulation(
        args.replay_dir,
        ticks=args.ticks,
        llm_backend=args.llm,
        model_id=args.model_id,
        embedder_backend=args.embedder,
        embedder_model_id=args.embed_model_id,
    )
    print(f"Run saved to {created_run}")


if __name__ == "__main__":
    main()


def _latest_run_folder(base_dir: Path) -> Path | None:
    if not base_dir.exists():
        return None
    run_dirs = [path for path in base_dir.iterdir() if path.is_dir()]
    if not run_dirs:
        return None
    return sorted(run_dirs)[-1]


def _replay_run(run_folder: Path) -> None:
    console = Console()
    log_path = run_folder / RUN_LOG_NAME
    for payload in read_tick_payloads(log_path):
        console.print(render_tick(payload))
