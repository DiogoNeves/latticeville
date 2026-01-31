"""Main Rich TUI viewer for ASCII world maps."""

from __future__ import annotations

import select
import sys
import termios
import time
import tty
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from typing import Iterable

from rich.console import Console, Group, RenderableType
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live

from latticeville.sim.contracts import TickPayload
from latticeville.sim.world_loader import WorldConfig, WorldPaths, load_world_config


@dataclass(frozen=True)
class AreaMap:
    area_id: str
    lines: list[str]
    width: int
    height: int
    portals: dict[str, str]


@dataclass
class MainViewerState:
    selected_agent_id: str | None = None
    speech_feed: deque[dict] = field(default_factory=lambda: deque(maxlen=20))
    agent_positions: dict[str, tuple[str, int, int]] = field(default_factory=dict)
    should_exit: bool = False


TILE_STYLES = {
    "#": "grey50",
    ".": "grey70",
    "+": "yellow",
    "=": "yellow",
    "~": "blue",
    "^": "red",
    "*": "bright_yellow",
    "T": "green",
    "B": "green",
    "1": "magenta",
    "2": "magenta",
    "3": "magenta",
    "4": "magenta",
    "5": "magenta",
    "6": "magenta",
    "7": "magenta",
    "8": "magenta",
    "9": "magenta",
}


def run_main_viewer(
    payloads: Iterable[TickPayload],
    *,
    config: WorldConfig | None = None,
    base_dir: Path | None = None,
    tick_delay: float = 0.2,
) -> None:
    config = config or load_world_config()
    base_dir = base_dir or WorldPaths().base_dir
    area_maps = _load_area_maps(config, base_dir)
    objects_by_area = _objects_by_area(config, area_maps)
    console = Console()
    state = MainViewerState()

    with _raw_terminal():
        with Live(console=console, auto_refresh=False, screen=True) as live:
            last_payload: TickPayload | None = None
            for payload in payloads:
                _handle_input(state, payload)
                renderable = _render(
                    payload,
                    config,
                    area_maps,
                    objects_by_area,
                    state,
                )
                last_payload = payload
                live.update(renderable, refresh=True)
                if state.should_exit:
                    break
                time.sleep(tick_delay)
            while last_payload is not None and not state.should_exit:
                _handle_input(state, last_payload)
                renderable = _render(
                    last_payload,
                    config,
                    area_maps,
                    objects_by_area,
                    state,
                )
                live.update(renderable, refresh=True)
                time.sleep(tick_delay)


def render_main_view(
    payload: TickPayload,
    *,
    config: WorldConfig | None = None,
    base_dir: Path | None = None,
    state: MainViewerState | None = None,
) -> RenderableType:
    config = config or load_world_config()
    base_dir = base_dir or WorldPaths().base_dir
    area_maps = _load_area_maps(config, base_dir)
    objects_by_area = _objects_by_area(config, area_maps)
    state = state or MainViewerState()
    return _render(payload, config, area_maps, objects_by_area, state)


def _render(
    payload: TickPayload,
    config: WorldConfig,
    area_maps: dict[str, AreaMap],
    objects_by_area: dict[str, list[dict]],
    state: MainViewerState,
) -> RenderableType:
    agent_ids = _agent_ids(payload)
    if state.selected_agent_id not in agent_ids:
        state.selected_agent_id = agent_ids[0] if agent_ids else None

    selected_area = _agent_area(payload, state.selected_agent_id)
    if selected_area is None:
        selected_area = next(iter(area_maps.keys()), "")

    _ingest_speech(payload, state)

    left = _render_speech_feed(state, selected_agent=state.selected_agent_id)
    center = _render_map(
        payload,
        config,
        area_maps,
        objects_by_area,
        state,
        selected_area=selected_area,
    )
    right = _render_selected_agent(payload, state.selected_agent_id)

    layout = Layout()
    layout.split_row(
        Layout(Panel(left, title="Speech"), ratio=2),
        Layout(Panel(center, title=f"World: {selected_area}"), ratio=5),
        Layout(Panel(right, title="Selected"), ratio=2),
    )
    return layout


def _render_map(
    payload: TickPayload,
    config: WorldConfig,
    area_maps: dict[str, AreaMap],
    objects_by_area: dict[str, list[dict]],
    state: MainViewerState,
    *,
    selected_area: str,
) -> RenderableType:
    area_map = area_maps[selected_area]
    grid = [list(line.ljust(area_map.width)) for line in area_map.lines]
    styles = [[TILE_STYLES.get(ch, "grey70") for ch in row] for row in grid]

    for obj in objects_by_area.get(selected_area, []):
        x, y = obj["x"], obj["y"]
        if 0 <= y < area_map.height and 0 <= x < area_map.width:
            grid[y][x] = obj["symbol"]
            styles[y][x] = "bright_yellow"

    agent_positions = _get_agent_positions(payload, area_maps, state)
    for agent_id, (area_id, x, y) in agent_positions.items():
        if area_id != selected_area:
            continue
        glyph = "@"
        style = "bright_cyan"
        if agent_id == state.selected_agent_id:
            style = "bright_green"
        if 0 <= y < area_map.height and 0 <= x < area_map.width:
            grid[y][x] = glyph
            styles[y][x] = style

    bubble = _latest_bubble(state, selected_area)
    bubble_map = {bubble["y"]: bubble["text"]} if bubble else {}

    lines: list[Text] = []
    for y, row in enumerate(grid):
        line = Text()
        for x, ch in enumerate(row):
            line.append(ch, style=styles[y][x])
        if y in bubble_map:
            line.append("  ")
            line.append(bubble_map[y], style="white on blue")
        lines.append(line)
    return Group(*lines)


def _render_speech_feed(
    state: MainViewerState, *, selected_agent: str | None
) -> RenderableType:
    table = Table(show_header=True, header_style="bold")
    table.add_column("Speaker")
    table.add_column("To")
    table.add_column("Utterance")
    for event in state.speech_feed:
        style = (
            "bold"
            if selected_agent in {event["agent_id"], event["to_agent_id"]}
            else ""
        )
        table.add_row(
            event["agent_id"],
            event["to_agent_id"],
            event["utterance"],
            style=style,
        )
    if not state.speech_feed:
        table.add_row("-", "-", "No speech yet.")
    return table


def _render_selected_agent(
    payload: TickPayload, agent_id: str | None
) -> RenderableType:
    table = Table(show_header=False)
    table.add_column("Field")
    table.add_column("Value")
    if agent_id is None:
        table.add_row("Agent", "None")
        return table
    node = payload.state.world.nodes.get(agent_id)
    area = payload.state.world.nodes.get(node.parent_id) if node else None
    table.add_row("Agent", node.name if node else agent_id)
    table.add_row("Area", area.name if area else "Unknown")
    belief = payload.state.beliefs.get(agent_id)
    if belief:
        area_names = sorted(
            {node.name for node in belief.nodes.values() if node.type == "area"}
        )
        table.add_row("Belief areas", ", ".join(area_names) or "None")
        table.add_row("Belief nodes", str(len(belief.nodes)))
    else:
        table.add_row("Belief", "No belief data")
    return table


def _load_area_maps(config: WorldConfig, base_dir: Path) -> dict[str, AreaMap]:
    maps: dict[str, AreaMap] = {}
    for area in config.areas:
        path = base_dir / area.map_file
        lines = path.read_text(encoding="utf-8").splitlines()
        width = max((len(line) for line in lines), default=0)
        height = len(lines)
        maps[area.id] = AreaMap(
            area_id=area.id,
            lines=lines,
            width=width,
            height=height,
            portals=area.portals,
        )
    return maps


def _objects_by_area(
    config: WorldConfig, area_maps: dict[str, AreaMap]
) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for obj in config.objects:
        if obj.position:
            x = obj.position.get("x", 0)
            y = obj.position.get("y", 0)
        elif obj.tile:
            area_map = area_maps.get(obj.area_id)
            x, y = _find_tile(area_map, obj.tile) if area_map else (1, 1)
        else:
            x, y = 1, 1
        grouped.setdefault(obj.area_id, []).append(
            {"symbol": obj.symbol, "x": x, "y": y}
        )
    return grouped


def _agent_ids(payload: TickPayload) -> list[str]:
    return sorted(
        node.id for node in payload.state.world.nodes.values() if node.type == "agent"
    )


def _agent_area(payload: TickPayload, agent_id: str | None) -> str | None:
    if agent_id is None:
        return None
    node = payload.state.world.nodes.get(agent_id)
    return node.parent_id if node else None


def _ingest_speech(payload: TickPayload, state: MainViewerState) -> None:
    for event in payload.events or []:
        if event.kind != "SAY":
            continue
        state.speech_feed.append(
            {
                "agent_id": event.payload.get("agent_id", ""),
                "to_agent_id": event.payload.get("to_agent_id", ""),
                "utterance": event.payload.get("utterance", ""),
                "area_id": event.payload.get("area_id", ""),
            }
        )


def _get_agent_positions(
    payload: TickPayload, area_maps: dict[str, AreaMap], state: MainViewerState
) -> dict[str, tuple[str, int, int]]:
    positions = dict(state.agent_positions)
    for agent_id in _agent_ids(payload):
        area_id = _agent_area(payload, agent_id) or next(iter(area_maps.keys()), "")
        area_map = area_maps.get(area_id)
        if area_map is None:
            continue
        spawn_points = _spawn_points(area_map)
        spawn_index = 0
        key = agent_id
        if key in positions and positions[key][0] == area_id:
            continue
        if spawn_points:
            x, y = spawn_points[spawn_index % len(spawn_points)]
            spawn_index += 1
        else:
            x, y = 1, 1
        positions[key] = (area_id, x, y)
    state.agent_positions = positions
    return positions


def _spawn_points(area_map: AreaMap) -> list[tuple[int, int]]:
    points: list[tuple[int, int]] = []
    for y, line in enumerate(area_map.lines):
        for x, ch in enumerate(line):
            if ch in {".", "+", "=", "1", "2", "3", "4", "5", "6", "7", "8", "9"}:
                points.append((x, y))
    return points


def _find_tile(area_map: AreaMap | None, tile: str) -> tuple[int, int]:
    if area_map is None:
        return (1, 1)
    for y, line in enumerate(area_map.lines):
        for x, ch in enumerate(line):
            if ch == tile:
                return (x, y)
    return (1, 1)


def _latest_bubble(state: MainViewerState, area_id: str) -> dict | None:
    for event in reversed(state.speech_feed):
        if event.get("area_id") != area_id:
            continue
        agent_id = event.get("agent_id")
        if not agent_id or agent_id not in state.agent_positions:
            continue
        _, _, y = state.agent_positions[agent_id]
        return {"text": _truncate(event.get("utterance", "")), "y": y}
    return None


def _truncate(text: str, limit: int = 24) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _handle_input(state: MainViewerState, payload: TickPayload) -> None:
    key = _read_key()
    if not key:
        return
    agent_ids = _agent_ids(payload)
    if not agent_ids:
        return
    if key in {"q", "Q"}:
        state.should_exit = True
        return
    if key == "]":
        state.selected_agent_id = _cycle(agent_ids, state.selected_agent_id, 1)
    if key == "[":
        state.selected_agent_id = _cycle(agent_ids, state.selected_agent_id, -1)


def _cycle(agent_ids: list[str], current: str | None, delta: int) -> str:
    if current not in agent_ids:
        return agent_ids[0]
    index = agent_ids.index(current)
    return agent_ids[(index + delta) % len(agent_ids)]


def _read_key() -> str | None:
    if not sys.stdin.isatty():
        return None
    ready, _, _ = select.select([sys.stdin], [], [], 0)
    if ready:
        return sys.stdin.read(1)
    return None


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
