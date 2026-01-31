"""Application entry for running the simulation loop."""

from pathlib import Path

from latticeville.db.replay_log import append_tick_payload
from latticeville.sim.tick_loop import run_ticks
from latticeville.sim.world_state import build_tiny_world


def run_simulation(log_path: Path, *, ticks: int = 10) -> None:
    state = build_tiny_world()
    for payload in run_ticks(state, ticks=ticks):
        append_tick_payload(log_path, payload)
