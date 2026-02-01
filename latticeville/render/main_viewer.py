"""Main Rich TUI viewer for the full world map."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from rich.align import Align
from rich.console import Console, Group, RenderableType
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live

from latticeville.render.terminal_input import raw_terminal, read_key
from latticeville.render.world_map import compute_viewport, render_map_lines
from latticeville.sim.contracts import TickPayload
from latticeville.sim.world_loader import WorldConfig, WorldPaths, load_world_config
from latticeville.sim.world_state import Bounds, ObjectState, WorldMap
from latticeville.sim.world_utils import resolve_area_name


LEFT_WIDTH = 32
RIGHT_WIDTH = 32


@dataclass
class MainViewerState:
    selected_agent_id: str | None = None
    event_feed: dict[str, deque[dict]] = field(default_factory=dict)
    character_hitboxes: list[tuple[int, int, str]] = field(default_factory=list)
    should_exit: bool = False
    camera_mode: str = "follow"
    camera_origin: tuple[int, int] = (0, 0)
    last_tick_seen: int | None = None


@dataclass(frozen=True)
class ViewerResources:
    config: WorldConfig
    world_map: WorldMap
    objects: dict[str, ObjectState]
    room_bounds: list[Bounds]


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
                _sync_state_for_payload(payload, state)
                paused = _handle_live_input(state, payload, paused, resources)
                if paused:
                    last_payload = payload
                    _render_and_update(live, payload, resources, state)
                    _pause_loop(live, payload, resources, state)
                    paused = False
                    continue
                renderable = _render_with_state(
                    payload, resources, state, frame_size=console.size
                )
                last_payload = payload
                live.update(_wrap_with_status(renderable, paused=False), refresh=True)
                if state.should_exit:
                    break
                time.sleep(tick_delay)
            while last_payload is not None and not state.should_exit:
                _sync_state_for_payload(last_payload, state)
                paused = _handle_live_input(state, last_payload, paused, resources)
                if paused:
                    _pause_loop(live, last_payload, resources, state)
                    paused = False
                    continue
                renderable = _render_with_state(
                    last_payload, resources, state, frame_size=console.size
                )
                live.update(_wrap_with_status(renderable, paused=False), refresh=True)
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
    _sync_state_for_payload(payload, state)
    return _render_with_state(payload, resources, state, frame_size=None)


# --- Private helpers ---


def _render_with_state(
    payload: TickPayload,
    resources: ViewerResources,
    state: MainViewerState,
    *,
    frame_size,
) -> RenderableType:
    agent_ids = _agent_ids(payload)
    if state.selected_agent_id not in agent_ids:
        state.selected_agent_id = agent_ids[0] if agent_ids else None

    left = _render_event_feed(state, selected_agent=state.selected_agent_id)
    center = _render_world_map(payload, resources, state, frame_size=frame_size)
    right, hitboxes = _render_right_panel(payload, state)
    state.character_hitboxes = hitboxes

    layout = Layout()
    layout.split_row(
        Layout(Panel(left, title="Events"), size=LEFT_WIDTH),
        Layout(Panel(center, title="World"), ratio=1),
        Layout(right, size=RIGHT_WIDTH),
    )
    return layout


def _render_world_map(
    payload: TickPayload,
    resources: ViewerResources,
    state: MainViewerState,
    *,
    frame_size,
) -> RenderableType:
    map_width, map_height = _map_panel_size(frame_size)
    selected_pos = _selected_agent_position(payload, state.selected_agent_id)

    if map_width >= resources.world_map.width and map_height >= resources.world_map.height:
        viewport = compute_viewport(
            resources.world_map.width,
            resources.world_map.height,
            resources.world_map.width,
            resources.world_map.height,
            origin=(0, 0),
        )
    else:
        if state.camera_mode == "follow" and selected_pos is not None:
            viewport = compute_viewport(
                resources.world_map.width,
                resources.world_map.height,
                map_width,
                map_height,
                center=selected_pos,
            )
            state.camera_origin = (viewport.x, viewport.y)
        else:
            viewport = compute_viewport(
                resources.world_map.width,
                resources.world_map.height,
                map_width,
                map_height,
                origin=state.camera_origin,
            )
            state.camera_origin = (viewport.x, viewport.y)

    lines = render_map_lines(
        resources.world_map,
        objects=resources.objects,
        agents=payload.state.agent_positions,
        selected_agent_id=state.selected_agent_id,
        viewport=viewport,
    )
    return Align.center(Group(*lines), vertical="middle")


def _map_panel_size(frame_size) -> tuple[int, int]:
    if frame_size is None:
        return (80, 24)
    width = max(10, frame_size.width - LEFT_WIDTH - RIGHT_WIDTH - 6)
    height = max(6, frame_size.height - 3)
    return (max(1, width - 2), max(1, height - 2))


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
    table.add_row("Room", area_name or "Unknown")
    position = payload.state.agent_positions.get(agent_id)
    if position:
        table.add_row("Pos", f"{position[0]}, {position[1]}")
    belief = payload.state.beliefs.get(agent_id)
    if belief:
        area_names = sorted(
            {node.name for node in belief.nodes.values() if node.type == "area"}
        )
        table.add_row("Belief rooms", ", ".join(area_names) or "None")
        table.add_row("Belief nodes", str(len(belief.nodes)))
    else:
        table.add_row("Belief", "No belief data")
    return table


def _load_viewer_resources(
    *, config: WorldConfig | None, base_dir: Path | None
) -> ViewerResources:
    config = config or load_world_config()
    base_dir = base_dir or WorldPaths().base_dir
    map_path = base_dir / config.map_file
    world_map = _load_world_map(map_path)
    objects = {
        obj.id: ObjectState(
            object_id=obj.id,
            name=obj.name,
            room_id=obj.room_id or "",
            symbol=obj.symbol,
            position=obj.position,
        )
        for obj in config.objects
    }
    room_bounds = [room.bounds for room in config.rooms]
    return ViewerResources(
        config=config,
        world_map=world_map,
        objects=objects,
        room_bounds=room_bounds,
    )


def _load_world_map(path: Path) -> WorldMap:
    lines = path.read_text(encoding="utf-8").splitlines()
    width = max((len(line) for line in lines), default=0)
    padded = [line.ljust(width) for line in lines]
    return WorldMap(lines=padded, width=width, height=len(padded))


def _agent_ids(payload: TickPayload) -> list[str]:
    return sorted(
        node.id for node in payload.state.world.nodes.values() if node.type == "agent"
    )


def _selected_agent_position(
    payload: TickPayload, agent_id: str | None
) -> tuple[int, int] | None:
    if agent_id is None:
        return None
    return payload.state.agent_positions.get(agent_id)


def _sync_state_for_payload(payload: TickPayload, state: MainViewerState) -> None:
    if state.last_tick_seen == payload.tick:
        return
    state.last_tick_seen = payload.tick
    _ingest_events(payload, state)


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


def _format_event(payload: TickPayload, event) -> str | None:
    kind = event.kind
    data = event.payload
    agent_id = data.get("agent_id")
    agent_name = _agent_name(payload, agent_id)
    if kind == "MOVE":
        from_id = data.get("from", "")
        to_id = data.get("to", "")
        return f"{agent_name} moved from {_room_name(payload, from_id)} to {_room_name(payload, to_id)}."
    if kind == "SAY":
        to_id = data.get("to_agent_id", "")
        utterance = data.get("utterance", "")
        return f'{agent_name} said to {_agent_name(payload, to_id)}: "{_truncate(utterance, 60)}"'
    if kind == "PLAN_SUMMARY":
        description = data.get("description", "")
        location_id = data.get("location", "")
        location = _room_name(payload, location_id)
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


def _room_name(payload: TickPayload, room_id: str | None) -> str:
    if not room_id:
        return "Unknown"
    node = payload.state.world.nodes.get(room_id)
    return node.name if node else room_id


def _truncate(text: str, limit: int = 24) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _handle_live_input(
    state: MainViewerState,
    payload: TickPayload,
    paused: bool,
    resources: ViewerResources,
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
        if key in {"f", "F"}:
            state.camera_mode = "follow"
        if agent_ids:
            if key == "]":
                state.selected_agent_id = _cycle(agent_ids, state.selected_agent_id, 1)
            if key == "[":
                state.selected_agent_id = _cycle(agent_ids, state.selected_agent_id, -1)
            if key.isdigit() and key != "0":
                selected = map_character_index(agent_ids, int(key) - 1)
                if selected:
                    state.selected_agent_id = selected
        if key in {"UP", "DOWN", "LEFT", "RIGHT"}:
            state.camera_mode = "pan"
            state.camera_origin = _pan_origin(
                state.camera_origin,
                key,
                resources.world_map.width,
                resources.world_map.height,
            )
    if event.kind == "mouse":
        agent = map_character_click(state.character_hitboxes, x=event.x, y=event.y)
        if agent:
            state.selected_agent_id = agent
    return paused


def _pan_origin(
    origin: tuple[int, int],
    key: str,
    width: int,
    height: int,
) -> tuple[int, int]:
    dx, dy = 0, 0
    if key == "UP":
        dy = -1
    elif key == "DOWN":
        dy = 1
    elif key == "LEFT":
        dx = -1
    elif key == "RIGHT":
        dx = 1
    return (_clamp(origin[0] + dx, 0, max(0, width - 1)), _clamp(origin[1] + dy, 0, max(0, height - 1)))


def _pause_loop(
    live: Live,
    payload: TickPayload,
    resources: ViewerResources,
    state: MainViewerState,
) -> None:
    while not state.should_exit:
        paused = _handle_live_input(state, payload, paused=True, resources=resources)
        renderable = _render_with_state(payload, resources, state, frame_size=live.console.size)
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
    renderable = _render_with_state(payload, resources, state, frame_size=live.console.size)
    live.update(_wrap_with_status(renderable, paused=True), refresh=True)


def _wrap_with_status(content: object, *, paused: bool) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(content, ratio=1),
        Layout(_render_status_bar(paused=paused), size=1),
    )
    return layout


def _render_status_bar(*, paused: bool) -> Panel:
    label = "paused" if paused else "live"
    text = Text(
        "Main controls: space=pause | q=quit | f=follow | arrows=pan | "
        "[/]=cycle | 1-9=select | status=" + label,
        style="bold",
    )
    return Panel(text, padding=(0, 1))


def _cycle(agent_ids: list[str], current: str | None, delta: int) -> str:
    if current not in agent_ids:
        return agent_ids[0]
    index = agent_ids.index(current)
    return agent_ids[(index + delta) % len(agent_ids)]


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


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))
