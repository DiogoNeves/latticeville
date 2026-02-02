"""Replay player loop for main viewer (Textual)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from latticeville.db.replay_log import RUN_LOG_NAME
from latticeville.render.main_viewer import BaseViewerScreen, _load_viewer_resources
from latticeville.render.replay_reader import read_tick_payloads
from latticeville.render.textual_app import LatticevilleApp
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


class ReplayPlayerScreen(BaseViewerScreen):
    BINDINGS = [
        ("space", "toggle_play", "Play/pause"),
        ("n", "step", "Step"),
        ("r", "restart", "Restart"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, run_folder: Path, *, tick_delay: float = 0.5) -> None:
        self._payloads = load_replay_payloads(run_folder / RUN_LOG_NAME)
        resources = _load_viewer_resources(config=None, base_dir=None)
        super().__init__(resources=resources)
        self._controller = ReplayController(last_tick=time.monotonic())
        self._tick_delay = tick_delay

    def on_mount(self) -> None:
        super().on_mount()
        if self._payloads:
            self._set_index(0)
        self.set_interval(0.05, self._tick)

    def _set_index(self, index: int) -> None:
        index = max(0, min(index, len(self._payloads) - 1))
        self._controller.index = index
        self._controller.last_tick = time.monotonic()
        self._update_payload(self._payloads[index])

    def _tick(self) -> None:
        if not self._payloads or not self._controller.playing:
            return
        if time.monotonic() - self._controller.last_tick < self._tick_delay:
            return
        if self._controller.index >= len(self._payloads) - 1:
            self._controller.playing = False
            return
        self._set_index(self._controller.index + 1)

    def action_toggle_play(self) -> None:
        self._controller.playing = not self._controller.playing
        self._controller.last_tick = time.monotonic()
        self._refresh_ui()

    def action_step(self) -> None:
        if not self._payloads:
            return
        self._controller.playing = False
        self._set_index(self._controller.index + 1)

    def action_restart(self) -> None:
        if not self._payloads:
            return
        self._controller.reset()
        self._set_index(0)

    def action_quit(self) -> None:
        self.app.exit()

    def _status_text(self) -> str:
        return "Replay controls: space=play/pause | n=step | r=restart | q=quit | [/]=cycle | 1-9=select"


def run_replay_player(
    run_folder: Path,
    *,
    tick_delay: float = 0.5,
) -> None:
    app = LatticevilleApp(
        ReplayPlayerScreen(run_folder, tick_delay=tick_delay),
        title="Latticeville Replay",
    )
    app.run()


def load_replay_payloads(log_path: Path) -> list[TickPayload]:
    return list(read_tick_payloads(log_path))
