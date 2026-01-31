"""Module entry point for `python -m latticeville`."""

from __future__ import annotations

import argparse
from pathlib import Path

from latticeville.app import run_simulation
from latticeville.render.live_tail import tail_replay_log

DEFAULT_LOG_PATH = Path("data/run-log.jsonl")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Latticeville simulation.")
    parser.add_argument(
        "--view",
        action="store_true",
        help="Tail the replay log and render the live viewer.",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help="Path to the JSONL replay log.",
    )
    parser.add_argument(
        "--ticks",
        type=int,
        default=10,
        help="Number of ticks to run (simulation mode only).",
    )
    args = parser.parse_args()

    if args.view:
        tail_replay_log(args.log_path)
    else:
        run_simulation(args.log_path, ticks=args.ticks)


if __name__ == "__main__":
    main()
