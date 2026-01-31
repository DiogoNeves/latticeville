"""Replay picker and player for main viewer."""

from __future__ import annotations

import json
import select
import sys
import termios
import time
import tty
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from rich.console import Console, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from latticeville.db.replay_log import RUN_LOG_NAME
from latticeville.render.main_viewer import MainViewerState, render_main_view
from latticeville.render.replay_reader import read_tick_payloads
from latticeville.sim.contracts import TickPayload


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


def pick_replay_run(base_dir: Path) -> Path | None:
    entries = list_replay_runs(base_dir)
    if not entries:
        return None
    console = Console()
    index = 0
    with _raw_terminal():
        with Live(console=console, auto_refresh=False, screen=True) as live:
            while True:
                live.update(_render_picker(entries, index), refresh=True)
                key = _read_key()
                if key is None:
                    time.sleep(0.05)
                    continue
                if key == "q":
                    return None
                if key == "UP":
                    index = (index - 1) % len(entries)
                if key == "DOWN":
                    index = (index + 1) % len(entries)
                if key == "ENTER":
                    return entries[index].run_dir


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
    playing = True
    index = 0
    last_tick = time.monotonic()

    with _raw_terminal():
        with Live(console=console, auto_refresh=False, screen=True) as live:
            while True:
                payload = payloads[index]
                renderable = render_main_view(payload, state=state)
                live.update(renderable, refresh=True)
                key = _read_key()
                if key == "q":
                    break
                if key == " ":
                    playing = not playing
                if key == "n":
                    playing = False
                    index = min(index + 1, len(payloads) - 1)
                if key == "r":
                    index = 0
                    state = MainViewerState()
                    playing = False
                if key in {"[", "]"}:
                    state.selected_agent_id = _cycle_agent(
                        payloads[index],
                        state.selected_agent_id,
                        1 if key == "]" else -1,
                    )

                if playing and time.monotonic() - last_tick >= tick_delay:
                    index = min(index + 1, len(payloads) - 1)
                    last_tick = time.monotonic()
                    if index == len(payloads) - 1:
                        playing = False
                time.sleep(0.05)


def load_replay_payloads(log_path: Path) -> list[TickPayload]:
    return list(read_tick_payloads(log_path))


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


def _read_key() -> str | None:
    if not sys.stdin.isatty():
        return None
    ready, _, _ = select.select([sys.stdin], [], [], 0)
    if not ready:
        return None
    key = sys.stdin.read(1)
    if key == "\x1b":
        seq = sys.stdin.read(2)
        if seq == "[A":
            return "UP"
        if seq == "[B":
            return "DOWN"
        return None
    if key in {"\r", "\n"}:
        return "ENTER"
    return key


@contextmanager
def _raw_terminal():
    if not sys.stdin.isatty():
        yield
        return
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
