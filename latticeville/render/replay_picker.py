"""Replay picker and player for main viewer."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from rich.console import Console, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from latticeville.db.replay_log import RUN_LOG_NAME
from latticeville.render.replay_player import run_replay_player
from latticeville.render.terminal_input import raw_terminal, read_key
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
    with raw_terminal():
        with Live(console=console, auto_refresh=False, screen=True) as live:
            while True:
                live.update(_render_picker(entries, index), refresh=True)
                event = read_key()
                if event is None:
                    time.sleep(0.05)
                    continue
                if event.kind != "key":
                    continue
                if event.key == "q":
                    return None
                if event.key == "UP":
                    index = (index - 1) % len(entries)
                if event.key == "DOWN":
                    index = (index + 1) % len(entries)
                if event.key == "ENTER":
                    return entries[index].run_dir


def pick_and_run_replay(base_dir: Path) -> None:
    run_folder = pick_replay_run(base_dir)
    if run_folder is None:
        return
    run_replay_player(run_folder)


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
