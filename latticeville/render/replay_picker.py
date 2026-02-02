"""Replay picker and player for main viewer (Textual)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from rich.console import RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static
from textual.containers import Vertical

from latticeville.db.replay_log import RUN_LOG_NAME
from latticeville.render.replay_player import ReplayPlayerScreen
from latticeville.render.textual_app import LatticevilleApp


@dataclass(frozen=True)
class ReplayEntry:
    run_dir: Path
    run_id: str
    ticks: int | None


def list_replay_runs(base_dir: Path) -> list[ReplayEntry]:
    if not base_dir.exists():
        return []
    entries: list[ReplayEntry] = []
    for path in sorted(base_dir.iterdir()):
        if not path.is_dir():
            continue
        log_path = path / RUN_LOG_NAME
        if not log_path.exists():
            continue
        run_id, ticks = _read_header(log_path)
        entries.append(
            ReplayEntry(
                run_dir=path,
                run_id=run_id or path.name,
                ticks=ticks,
            )
        )
    return entries


class ReplayPickerScreen(Screen):
    CSS = """
    Screen {
        layout: vertical;
    }
    #picker {
        height: 1fr;
    }
    #status-bar {
        height: 3;
    }
    """

    BINDINGS = [
        ("up", "move_up", "Up"),
        ("down", "move_down", "Down"),
        ("enter", "select", "Select"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, base_dir: Path) -> None:
        super().__init__()
        self._base_dir = base_dir
        self._entries = list_replay_runs(base_dir)
        self._index = 0
        self._picker: Static | None = None
        self._status_bar: Static | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="root"):
            yield Static(id="picker")
            yield Static(id="status-bar")

    def on_mount(self) -> None:
        self._picker = self.query_one("#picker", Static)
        self._status_bar = self.query_one("#status-bar", Static)
        self._refresh()

    def _refresh(self) -> None:
        if self._picker:
            if not self._entries:
                self._picker.update(
                    Panel(Text("No replay runs found."), title="Replay Picker")
                )
            else:
                self._picker.update(_render_picker(self._entries, self._index))
        if self._status_bar:
            self._status_bar.update(
                Panel(
                    Text("Replay picker: up/down=move | enter=select | q=quit"),
                    padding=(0, 1),
                )
            )

    def action_move_up(self) -> None:
        if not self._entries:
            return
        self._index = (self._index - 1) % len(self._entries)
        self._refresh()

    def action_move_down(self) -> None:
        if not self._entries:
            return
        self._index = (self._index + 1) % len(self._entries)
        self._refresh()

    def action_select(self) -> None:
        if not self._entries:
            return
        run_folder = self._entries[self._index].run_dir
        self.app.push_screen(ReplayPlayerScreen(run_folder))

    def action_quit(self) -> None:
        self.app.exit()


def pick_and_run_replay(base_dir: Path) -> None:
    app = LatticevilleApp(
        ReplayPickerScreen(base_dir), title="Latticeville Replay Picker"
    )
    app.run()


def _render_picker(entries: list[ReplayEntry], index: int) -> RenderableType:
    table = Table(title="Select a replay (up/down, enter, q)", show_header=True)
    table.add_column("Run ID")
    table.add_column("Ticks")
    for idx, entry in enumerate(entries):
        style = "reverse" if idx == index else ""
        table.add_row(
            entry.run_id,
            str(entry.ticks) if entry.ticks is not None else "-",
            style=style,
        )
    return Panel(table, title="Replay Picker")


def _read_header(log_path: Path) -> tuple[str | None, int | None]:
    try:
        line = log_path.read_text(encoding="utf-8").splitlines()[0]
        record = json.loads(line)
    except (IndexError, FileNotFoundError, json.JSONDecodeError):
        return None, None
    metadata = record.get("metadata", {})
    return metadata.get("run_id"), metadata.get("ticks")

