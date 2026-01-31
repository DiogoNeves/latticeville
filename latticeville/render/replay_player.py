"""Replay player loop for main viewer."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text

from latticeville.db.replay_log import RUN_LOG_NAME
from latticeville.render.main_viewer import (
    MainViewerState,
    map_character_click,
    map_character_index,
    render_main_view,
)
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
                live.update(_wrap_with_status(renderable), refresh=True)
                event = read_key()
                if event and event.kind == "key" and event.key == "q":
                    break
                if event and event.kind == "key" and event.key == " ":
                    controller.playing = not controller.playing
                if event and event.kind == "key" and event.key == "n":
                    controller.playing = False
                    controller.index = min(controller.index + 1, len(payloads) - 1)
                if event and event.kind == "key" and event.key == "r":
                    controller.reset()
                    state = MainViewerState()
                if event and event.kind == "key" and event.key in {"[", "]"}:
                    state.selected_agent_id = _cycle_agent(
                        payloads[controller.index],
                        state.selected_agent_id,
                        1 if event.key == "]" else -1,
                    )
                if (
                    event
                    and event.kind == "key"
                    and event.key
                    and event.key.isdigit()
                    and event.key != "0"
                ):
                    agent_ids = _agent_ids(payloads[controller.index])
                    selected = map_character_index(agent_ids, int(event.key) - 1)
                    if selected:
                        state.selected_agent_id = selected
                if event and event.kind == "mouse":
                    agent = map_character_click(
                        state.character_hitboxes, x=event.x, y=event.y
                    )
                    if agent:
                        state.selected_agent_id = agent

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


def _agent_ids(payload: TickPayload) -> list[str]:
    return sorted(
        node.id for node in payload.state.world.nodes.values() if node.type == "agent"
    )


def _wrap_with_status(content: object) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(content, ratio=1),
        Layout(_render_status_bar(), size=3),
    )
    return layout


def _render_status_bar() -> Panel:
    text = Text(
        "Replay controls: space=play/pause | n=step | r=restart | q=quit | [/]=cycle",
        style="bold",
    )
    return Panel(text, padding=(0, 1))
