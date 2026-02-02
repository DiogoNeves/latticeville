"""Tail a JSONL replay log and render latest-frame output (Textual)."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from rich.panel import Panel
from rich.text import Text
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static
from textual.containers import Vertical

from latticeville.render.textual_app import LatticevilleApp
from latticeville.render.viewer import render_tick
from latticeville.sim.contracts import TickPayload


class TailViewerScreen(Screen):
    CSS = """
    Screen {
        layout: vertical;
    }
    #tail-view {
        height: 1fr;
    }
    """

    def __init__(self, path: Path, *, poll_interval: float = 0.2) -> None:
        super().__init__()
        self._path = path
        self._poll_interval = poll_interval
        self._view: Static | None = None
        self._stop_event = threading.Event()

    def compose(self) -> ComposeResult:
        with Vertical(id="root"):
            yield Static(id="tail-view")

    def on_mount(self) -> None:
        self._view = self.query_one("#tail-view", Static)
        if self._view:
            self._view.update(
                Panel(Text("Waiting for replay data..."), title="Live Replay")
            )
        self._start_tail()

    def on_unmount(self) -> None:
        self._stop_event.set()

    def _start_tail(self) -> None:
        thread = threading.Thread(target=self._tail_loop, daemon=True)
        thread.start()

    def _tail_loop(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("r", encoding="utf-8") as handle:
            handle.seek(0, 2)
            while not self._stop_event.is_set():
                line = handle.readline()
                if not line:
                    time.sleep(self._poll_interval)
                    continue
                record = _parse_record(line)
                if record is None or record.get("type") != "tick":
                    continue
                payload = record.get("payload")
                if payload is None:
                    continue
                tick_payload = TickPayload.model_validate(payload)
                self.app.call_from_thread(self._update_payload, tick_payload)

    def _update_payload(self, payload: TickPayload) -> None:
        if self._view:
            self._view.update(render_tick(payload))


def tail_replay_log(path: Path, *, poll_interval: float = 0.2) -> None:
    app = LatticevilleApp(
        TailViewerScreen(path, poll_interval=poll_interval), title="Latticeville Tail"
    )
    app.run()


def _parse_record(line: str) -> dict[str, Any] | None:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None
