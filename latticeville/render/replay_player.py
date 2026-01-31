"""Replay player loop for main viewer."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.live import Live

from latticeville.db.replay_log import RUN_LOG_NAME
from latticeville.render.main_viewer import MainViewerState, render_main_view
from latticeville.render.replay_reader import read_tick_payloads
from latticeville.render.terminal_input import raw_terminal, read_key
from latticeville.sim.contracts import TickPayload


@dataclass
class ReplayController:
    playing: bool = True
    index: int = 0
    last_tick: float = 0.0

    def reset(self) -> None:
        self.playing = False
        self.index = 0
        self.last_tick = time.monotonic()


def run_replay_player(
    run_folder: Path,
    *,
    tick_delay: float = 0.5,
) -> None:
    log_path = run_folder / RUN_LOG_NAME
    payloads = load_replay_payloads(log_path)
    if not payloads:
        return
    state = MainViewerState()
    console = Console()
    controller = ReplayController(last_tick=time.monotonic())

    with raw_terminal():
        with Live(console=console, auto_refresh=False, screen=True) as live:
            while True:
                payload = payloads[controller.index]
                renderable = render_main_view(payload, state=state)
                live.update(renderable, refresh=True)
                key = read_key()
                if key == "q":
                    break
                if key == " ":
                    controller.playing = not controller.playing
                if key == "n":
                    controller.playing = False
                    controller.index = min(controller.index + 1, len(payloads) - 1)
                if key == "r":
                    controller.reset()
                    state = MainViewerState()
                if key in {"[", "]"}:
                    state.selected_agent_id = _cycle_agent(
                        payloads[controller.index],
                        state.selected_agent_id,
                        1 if key == "]" else -1,
                    )

                _advance(controller, payloads, tick_delay)
                time.sleep(0.05)


def load_replay_payloads(log_path: Path) -> list[TickPayload]:
    return list(read_tick_payloads(log_path))


def _advance(
    controller: ReplayController, payloads: list[TickPayload], tick_delay: float
) -> None:
    if not controller.playing:
        return
    if time.monotonic() - controller.last_tick < tick_delay:
        return
    controller.index = min(controller.index + 1, len(payloads) - 1)
    controller.last_tick = time.monotonic()
    if controller.index == len(payloads) - 1:
        controller.playing = False


def _cycle_agent(payload: TickPayload, current: str | None, delta: int) -> str | None:
    agent_ids = sorted(
        node.id for node in payload.state.world.nodes.values() if node.type == "agent"
    )
    if not agent_ids:
        return None
    if current not in agent_ids:
        return agent_ids[0]
    index = agent_ids.index(current)
    return agent_ids[(index + delta) % len(agent_ids)]
