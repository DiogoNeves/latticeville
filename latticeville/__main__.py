"""Module entry point for `python -m latticeville`."""

from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from latticeville.app import run_simulation
from latticeville.db.replay_log import RUN_LOG_NAME
from latticeville.render.live_tail import tail_replay_log
from latticeville.render.replay_reader import read_tick_payloads
from latticeville.render.viewer import render_tick

DEFAULT_REPLAY_DIR = Path("replay")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Latticeville simulation.")
    parser.add_argument(
        "--view",
        action="store_true",
        help="Tail a replay log and render the live viewer.",
    )
    parser.add_argument(
        "--replay",
        type=Path,
        default=None,
        help="Replay a saved run folder through the viewer.",
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
        "--ticks",
        type=int,
        default=10,
        help="Number of ticks to run (simulation mode only).",
    )
    args = parser.parse_args()

    if args.view:
        run_folder = args.run_folder or _latest_run_folder(args.replay_dir)
        if run_folder is None:
            raise SystemExit("No run folder found. Run a simulation first.")
        tail_replay_log(run_folder / RUN_LOG_NAME)
        return

    if args.replay is not None:
        run_folder = args.replay
    else:
        run_folder = args.run_folder

    if run_folder:
        _replay_run(run_folder)
        return

    created_run = run_simulation(args.replay_dir, ticks=args.ticks)
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
