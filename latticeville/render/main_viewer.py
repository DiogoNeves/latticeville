"""Main Rich TUI viewer for ASCII world maps."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from typing import Iterable

from rich.console import Console, Group, RenderableType
from rich.align import Align
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live

from latticeville.render.terminal_input import raw_terminal, read_key
from latticeville.sim.contracts import TickPayload
from latticeville.sim.world_utils import resolve_area_id, resolve_area_name
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
    event_feed: dict[str, deque[dict]] = field(default_factory=dict)
    agent_positions: dict[str, tuple[str, int, int]] = field(default_factory=dict)
    character_hitboxes: list[tuple[int, int, str]] = field(default_factory=list)
    should_exit: bool = False
    view_mode: str = "local"
    last_tick_seen: int | None = None


@dataclass(frozen=True)
class ViewerResources:
    config: WorldConfig
    area_maps: dict[str, AreaMap]
    overview_map: AreaMap | None
    objects_by_area: dict[str, list[dict]]


@dataclass(frozen=True)
class RenderFrame:
    renderable: RenderableType
    hitboxes: list[tuple[int, int, str]]


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
    resources = _load_viewer_resources(config=config, base_dir=base_dir)
    console = Console()
    state = MainViewerState()

    with raw_terminal():
        with Live(console=console, auto_refresh=False, screen=True) as live:
            paused = False
            last_payload: TickPayload | None = None
            for payload in payloads:
                _sync_state_for_payload(payload, state, resources)
                paused = _handle_live_input(state, payload, paused)
                if paused:
                    last_payload = payload
                    _render_and_update(
                        live,
                        payload,
                        resources,
                        state,
                    )
                    _pause_loop(
                        live,
                        payload,
                        resources,
                        state,
                    )
                    paused = False
                    continue
                renderable = _render_with_state(payload, resources, state)
                last_payload = payload
                live.update(_wrap_with_status(renderable), refresh=True)
                if state.should_exit:
                    break
                time.sleep(tick_delay)
            while last_payload is not None and not state.should_exit:
                _sync_state_for_payload(last_payload, state, resources)
                paused = _handle_live_input(state, last_payload, paused)
                if paused:
                    _pause_loop(
                        live,
                        last_payload,
                        resources,
                        state,
                    )
                    paused = False
                    continue
                renderable = _render_with_state(last_payload, resources, state)
                live.update(_wrap_with_status(renderable), refresh=True)
                time.sleep(tick_delay)


def render_main_view(
    payload: TickPayload,
    *,
    config: WorldConfig | None = None,
    base_dir: Path | None = None,
    state: MainViewerState | None = None,
) -> RenderableType:
    resources = _load_viewer_resources(config=config, base_dir=base_dir)
    state = state or MainViewerState()
    _sync_state_for_payload(payload, state, resources)
    return _render_with_state(payload, resources, state)


# --- Private helpers ---


def _render_frame(
    payload: TickPayload,
    resources: ViewerResources,
    state: MainViewerState,
) -> RenderFrame:
    selected_area = _agent_area(payload, state.selected_agent_id)
    if selected_area is None:
        selected_area = next(iter(resources.area_maps.keys()), "")

    left = _render_event_feed(state, selected_agent=state.selected_agent_id)
    if state.view_mode == "overview" and resources.overview_map is not None:
        center = _render_overview_map(
            payload,
            resources.config,
            resources.overview_map,
            selected_area=selected_area,
        )
        title = "World: overview"
    else:
        center = _render_map(
            resources.area_maps,
            resources.objects_by_area,
            state,
            selected_area=selected_area,
        )
        title = f"World: {selected_area}"
    right, hitboxes = _render_right_panel(payload, state)

    layout = Layout()
    layout.split_row(
        Layout(Panel(left, title="Events"), ratio=2),
        Layout(Panel(center, title=title), ratio=5),
        Layout(right, ratio=2),
    )
    return RenderFrame(renderable=layout, hitboxes=hitboxes)


def _render_with_state(
    payload: TickPayload,
    resources: ViewerResources,
    state: MainViewerState,
) -> RenderableType:
    frame = _render_frame(payload, resources, state)
    state.character_hitboxes = frame.hitboxes
    return frame.renderable


def _render_map(
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

    for agent_id, (area_id, x, y) in state.agent_positions.items():
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
    return Align.center(Group(*lines), vertical="middle")


def _render_overview_map(
    payload: TickPayload,
    config: WorldConfig,
    overview_map: AreaMap,
    *,
    selected_area: str,
) -> RenderableType:
    grid = [list(line.ljust(overview_map.width)) for line in overview_map.lines]
    styles = [[TILE_STYLES.get(ch, "grey70") for ch in row] for row in grid]
    area_counts = _area_counts(payload)
    for area in config.areas:
        anchor = area.overview_anchor
        if not anchor:
            continue
        x, y = anchor.get("x", 0), anchor.get("y", 0)
        if not (0 <= y < overview_map.height and 0 <= x < overview_map.width):
            continue
        count = area_counts.get(area.id, 0)
        if count > 1:
            glyph = str(min(count, 9))
        else:
            glyph = (area.overview_symbol or area.id[:1] or "?")[:1]
        style = "bright_white"
        if area.id == selected_area:
            style = "bold bright_green"
        grid[y][x] = glyph
        styles[y][x] = style
    lines: list[Text] = []
    for y, row in enumerate(grid):
        line = Text()
        for x, ch in enumerate(row):
            line.append(ch, style=styles[y][x])
        lines.append(line)
    return Align.center(Group(*lines), vertical="middle")


def _render_event_feed(
    state: MainViewerState, *, selected_agent: str | None
) -> RenderableType:
    table = Table(show_header=True, header_style="bold")
    table.add_column("Tick", justify="right", width=6)
    table.add_column("Event")
    feed = state.event_feed.get(selected_agent or "", deque())
    for entry in feed:
        table.add_row(str(entry.get("tick", "")), entry.get("text", ""))
    if not feed:
        table.add_row("-", "No events yet.")
    return table


def _render_right_panel(
    payload: TickPayload, state: MainViewerState
) -> tuple[RenderableType, list[tuple[int, int, str]]]:
    agents = _agent_ids(payload)
    list_panel, hitboxes = _render_character_list(
        payload, agents, state.selected_agent_id
    )
    selected_panel = _render_selected_agent(payload, state.selected_agent_id)

    right = Layout()
    row_count = max(1, len(agents))
    per_row = 1
    header_rows = 1
    global_offset = 3
    list_height = row_count * per_row + header_rows + global_offset + 2
    right.split_column(
        Layout(list_panel, size=list_height),
        Layout(selected_panel),
    )
    return right, hitboxes


def _render_character_list(
    payload: TickPayload, agents: list[str], selected: str | None
) -> tuple[RenderableType, list[tuple[int, int, str]]]:
    table = Table(show_header=True, header_style="bold")
    table.add_column("Characters")
    hitboxes: list[tuple[int, int, str]] = []
    for index, agent_id in enumerate(agents):
        node = payload.state.world.nodes.get(agent_id)
        name = node.name if node else agent_id
        if index < 9:
            name = f"{index + 1}. {name}"
        style = "reverse" if agent_id == selected else ""
        table.add_row(name, style=style)
        hitboxes.append((index + 1, 1, agent_id))
    if not agents:
        table.add_row("None")
    return Panel(table, title="Characters"), hitboxes


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
    table.add_row("Agent", node.name if node else agent_id)
    area_name = resolve_area_name(payload.state.world, agent_id)
    table.add_row("Area", area_name or "Unknown")
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


def _load_overview_map(config: WorldConfig, base_dir: Path) -> AreaMap | None:
    map_file = config.overview_map_file
    if not map_file:
        return None
    path = base_dir / map_file
    lines = path.read_text(encoding="utf-8").splitlines()
    width = max((len(line) for line in lines), default=0)
    height = len(lines)
    return AreaMap(
        area_id="overview",
        lines=lines,
        width=width,
        height=height,
        portals={},
    )


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
    return resolve_area_id(payload.state.world, agent_id)


def _area_counts(payload: TickPayload) -> dict[str, int]:
    counts: dict[str, int] = {}
    for agent_id in _agent_ids(payload):
        area_id = _agent_area(payload, agent_id)
        if not area_id:
            continue
        counts[area_id] = counts.get(area_id, 0) + 1
    return counts


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


def _ingest_events(payload: TickPayload, state: MainViewerState) -> None:
    for event in payload.events or []:
        agent_id = event.payload.get("agent_id")
        if not agent_id:
            continue
        text = _format_event(payload, event)
        if not text:
            continue
        feed = state.event_feed.get(agent_id)
        if feed is None:
            feed = deque(maxlen=40)
            state.event_feed[agent_id] = feed
        feed.append({"tick": payload.tick, "text": text})


def _compute_agent_positions(
    payload: TickPayload,
    area_maps: dict[str, AreaMap],
    previous: dict[str, tuple[str, int, int]],
) -> dict[str, tuple[str, int, int]]:
    positions = dict(previous)
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


def map_character_click(
    hitboxes: list[tuple[int, int, str]],
    *,
    x: int | None,
    y: int | None,
) -> str | None:
    if x is None or y is None:
        return None
    for row, col, agent_id in hitboxes:
        if y == row and x >= col:
            return agent_id
    return None


def map_character_index(agents: list[str], index: int) -> str | None:
    if index < 0 or index >= len(agents):
        return None
    return agents[index]


def _handle_live_input(
    state: MainViewerState, payload: TickPayload, paused: bool
) -> bool:
    event = read_key()
    if not event:
        return paused
    agent_ids = _agent_ids(payload)
    if event.kind == "key":
        key = event.key or ""
        if key == " ":
            return not paused
        if key in {"q", "Q"}:
            state.should_exit = True
            return paused
        if key in {"o", "O"}:
            state.view_mode = "overview" if state.view_mode == "local" else "local"
        if agent_ids:
            if key == "]":
                state.selected_agent_id = _cycle(agent_ids, state.selected_agent_id, 1)
            if key == "[":
                state.selected_agent_id = _cycle(agent_ids, state.selected_agent_id, -1)
            if key.isdigit() and key != "0":
                selected = map_character_index(agent_ids, int(key) - 1)
                if selected:
                    state.selected_agent_id = selected
    if event.kind == "mouse":
        agent = map_character_click(state.character_hitboxes, x=event.x, y=event.y)
        if agent:
            state.selected_agent_id = agent
    return paused


def _pause_loop(
    live: Live,
    payload: TickPayload,
    resources: ViewerResources,
    state: MainViewerState,
) -> None:
    while not state.should_exit:
        _sync_state_for_payload(payload, state, resources)
        paused = _handle_live_input(state, payload, paused=True)
        renderable = _render_with_state(payload, resources, state)
        live.update(_wrap_with_status(renderable, paused=True), refresh=True)
        if not paused:
            break
        time.sleep(0.05)


def _render_and_update(
    live: Live,
    payload: TickPayload,
    resources: ViewerResources,
    state: MainViewerState,
) -> None:
    renderable = _render_with_state(payload, resources, state)
    live.update(_wrap_with_status(renderable), refresh=True)


def _wrap_with_status(content: object, *, paused: bool = False) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(content, ratio=1),
        Layout(_render_status_bar(paused=paused), size=1),
    )
    return layout


def _render_status_bar(*, paused: bool) -> Panel:
    label = "paused" if paused else "live"
    text = Text(
        "Main controls: space=pause/resume | q=quit | o=overview | "
        f"[/]=cycle | 1-9=select | status={label}",
        style="bold",
    )
    return Panel(text, padding=(0, 1))


def _cycle(agent_ids: list[str], current: str | None, delta: int) -> str:
    if current not in agent_ids:
        return agent_ids[0]
    index = agent_ids.index(current)
    return agent_ids[(index + delta) % len(agent_ids)]


def _load_viewer_resources(
    *, config: WorldConfig | None, base_dir: Path | None
) -> ViewerResources:
    config = config or load_world_config()
    base_dir = base_dir or WorldPaths().base_dir
    area_maps = _load_area_maps(config, base_dir)
    overview_map = _load_overview_map(config, base_dir)
    objects_by_area = _objects_by_area(config, area_maps)
    return ViewerResources(
        config=config,
        area_maps=area_maps,
        overview_map=overview_map,
        objects_by_area=objects_by_area,
    )


def _sync_state_for_payload(
    payload: TickPayload,
    state: MainViewerState,
    resources: ViewerResources,
) -> None:
    agent_ids = _agent_ids(payload)
    if state.selected_agent_id not in agent_ids:
        state.selected_agent_id = agent_ids[0] if agent_ids else None
    if state.last_tick_seen == payload.tick:
        return
    state.last_tick_seen = payload.tick
    _ingest_speech(payload, state)
    _ingest_events(payload, state)
    state.agent_positions = _compute_agent_positions(
        payload, resources.area_maps, state.agent_positions
    )


def _format_event(payload: TickPayload, event) -> str | None:
    kind = event.kind
    data = event.payload
    agent_id = data.get("agent_id")
    agent_name = _agent_name(payload, agent_id)
    if kind == "MOVE":
        from_id = data.get("from", "")
        to_id = data.get("to", "")
        return f"{agent_name} moved from {_area_name(payload, from_id)} to {_area_name(payload, to_id)}."
    if kind == "SAY":
        to_id = data.get("to_agent_id", "")
        utterance = data.get("utterance", "")
        return f'{agent_name} said to {_agent_name(payload, to_id)}: "{_truncate(utterance, 60)}"'
    if kind == "PLAN_SUMMARY":
        description = data.get("description", "")
        location_id = data.get("location", "")
        location = _area_name(payload, location_id)
        time_window = data.get("time_window", "")
        level = data.get("level", "action")
        return (
            f"Plan [{level}] ({time_window} @ {location}): "
            f"{_truncate(description, 70)}"
        )
    if kind == "REFLECTION_SUMMARY":
        count = data.get("count", 0)
        items = data.get("items", [])
        preview = _truncate(items[0], 70) if items else "No insights."
        return f"Reflected ({count}): {preview}"
    return None


def _agent_name(payload: TickPayload, agent_id: str | None) -> str:
    if not agent_id:
        return "Unknown"
    node = payload.state.world.nodes.get(agent_id)
    return node.name if node else agent_id


def _area_name(payload: TickPayload, area_id: str | None) -> str:
    if not area_id:
        return "Unknown"
    name = resolve_area_name(payload.state.world, area_id)
    return name if name else area_id
