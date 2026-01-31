"""Application entry for running the simulation loop."""

from pathlib import Path

from latticeville.db.replay_log import (
    append_tick_payload,
    create_run_folder,
    write_header,
)
from latticeville.sim.tick_loop import run_ticks
from latticeville.sim.world_state import build_tiny_world


def run_simulation(base_dir: Path, *, ticks: int = 10) -> Path:
    run_dir, log_path = create_run_folder(base_dir)
    write_header(
        log_path,
        metadata={
            "run_id": run_dir.name,
            "created_at": run_dir.name,
            "ticks": ticks,
        },
    )
    state = build_tiny_world()
    for payload in run_ticks(state, ticks=ticks):
        append_tick_payload(log_path, payload)
    return run_dir
