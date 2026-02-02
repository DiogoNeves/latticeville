"""Main Rich TUI viewer for the full world map."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from rich.align import Align
from rich.console import Group, RenderableType
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.events import Key
from textual.screen import Screen
from textual.widgets import Label, ListItem, ListView, Static
from textual.containers import Horizontal, Vertical

from latticeville.render.textual_app import LatticevilleApp
from latticeville.render.textual_widgets import MapRenderResult, MapWidget
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
    last_reload_at: float | None = None


@dataclass(frozen=True)
class ViewerResources:
    config: WorldConfig
    world_map: WorldMap
    objects: dict[str, ObjectState]
    room_bounds: list[Bounds]
    world_json_path: Path
    map_path: Path
    world_json_mtime: float | None
    map_mtime: float | None


class AgentListItem(ListItem):
    def __init__(self, agent_id: str, label: str) -> None:
        super().__init__(Label(label))
        self.agent_id = agent_id


class BaseViewerScreen(Screen):
    CSS = """
    Screen {
        layout: vertical;
    }
    #main {
        layout: horizontal;
        height: 1fr;
    }
    #right-pane {
        layout: vertical;
    }
    #status-bar {
        height: 3;
    }
    """

    def __init__(
        self,
        *,
        resources: ViewerResources,
        state: MainViewerState | None = None,
    ) -> None:
        super().__init__()
        self.resources = resources
        self.state = state or MainViewerState()
        self.payload: TickPayload | None = None
        self._events_panel: Static | None = None
        self._map_widget: MapWidget | None = None
        self._agent_list: ListView | None = None
        self._agent_details: Static | None = None
        self._status_bar: Static | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="root"):
            with Horizontal(id="main"):
                yield Static(id="events-pane")
                yield MapWidget(self._render_map, id="world-map")
                with Vertical(id="right-pane"):
                    yield ListView(id="agent-list")
                    yield Static(id="agent-details")
            yield Static(id="status-bar")

    def on_mount(self) -> None:
        self._events_panel = self.query_one("#events-pane", Static)
        self._map_widget = self.query_one("#world-map", MapWidget)
        self._agent_list = self.query_one("#agent-list", ListView)
        self._agent_details = self.query_one("#agent-details", Static)
        self._status_bar = self.query_one("#status-bar", Static)
        if self._events_panel:
            self._events_panel.styles.width = LEFT_WIDTH
        right_pane = self.query_one("#right-pane")
        right_pane.styles.width = RIGHT_WIDTH
        if self._agent_list:
            self._agent_list.styles.height = "1fr"
            self._agent_list.can_focus = False
        if self._agent_details:
            self._agent_details.styles.height = "1fr"
        self._refresh_ui()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self._select_from_list(event.item)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        self._select_from_list(event.item)

    def _select_from_list(self, item: ListItem | None) -> None:
        if not isinstance(item, AgentListItem):
            return
        self.state.selected_agent_id = item.agent_id
        self._refresh_ui()

    def on_key(self, event: Key) -> None:
        if self.payload is None:
            return
        if event.key in {"[", "]"}:
            agent_ids = _agent_ids(self.payload)
            delta = 1 if event.key == "]" else -1
            self.state.selected_agent_id = _cycle(
                agent_ids, self.state.selected_agent_id, delta
            )
            self._refresh_ui()
            event.stop()
            return
        if event.character and event.character.isdigit() and event.character != "0":
            agent_ids = _agent_ids(self.payload)
            selected = map_character_index(agent_ids, int(event.character) - 1)
            if selected:
                self.state.selected_agent_id = selected
                self._refresh_ui()
            event.stop()

    def _update_payload(self, payload: TickPayload) -> None:
        self.payload = payload
        agent_ids = _agent_ids(payload)
        if self.state.selected_agent_id not in agent_ids:
            self.state.selected_agent_id = agent_ids[0] if agent_ids else None
        _sync_state_for_payload(payload, self.state)
        self._refresh_ui()

    def _refresh_ui(self) -> None:
        if self.payload is None:
            if self._events_panel:
                self._events_panel.update(
                    Panel(Text("Waiting for data."), title="Events")
                )
            if self._agent_details:
                self._agent_details.update(
                    Panel(Text("No agent selected."), title="Selected")
                )
            if self._status_bar:
                self._status_bar.update(
                    Panel(Text(self._status_text()), padding=(0, 1))
                )
            if self._map_widget:
                self._map_widget.refresh()
            return
        if self._events_panel:
            self._events_panel.update(
                Panel(
                    _render_event_feed(
                        self.state, selected_agent=self.state.selected_agent_id
                    ),
                    title="Events",
                )
            )
        if self._agent_details:
            self._agent_details.update(
                Panel(
                    _render_selected_agent(self.payload, self.state.selected_agent_id),
                    title="Selected",
                )
            )
        self._update_agent_list(self.payload)
        if self._status_bar:
            self._status_bar.update(Panel(Text(self._status_text()), padding=(0, 1)))
        if self._map_widget:
            self._map_widget.refresh()

    def _update_agent_list(self, payload: TickPayload) -> None:
        if not self._agent_list:
            return
        agent_ids = _agent_ids(payload)
        self._agent_list.clear()
        for index, agent_id in enumerate(agent_ids):
            node = payload.state.world.nodes.get(agent_id)
            name = node.name if node else agent_id
            label = f"{index + 1}. {name}" if index < 9 else name
            self._agent_list.append(AgentListItem(agent_id, label))
        if agent_ids and self.state.selected_agent_id in agent_ids:
            self._agent_list.index = agent_ids.index(self.state.selected_agent_id)

    def _render_map(self, size, content_size) -> MapRenderResult:
        inner_width = max(1, content_size.width - 2)
        inner_height = max(1, content_size.height - 2)
        payload = self.payload
        selected_pos = None
        agents = {}
        if payload:
            selected_pos = _selected_agent_position(
                payload, self.state.selected_agent_id
            )
            agents = payload.state.agent_positions

        if (
            inner_width >= self.resources.world_map.width
            and inner_height >= self.resources.world_map.height
        ):
            viewport = compute_viewport(
                self.resources.world_map.width,
                self.resources.world_map.height,
                self.resources.world_map.width,
                self.resources.world_map.height,
                origin=(0, 0),
            )
        else:
            if self.state.camera_mode == "follow" and selected_pos is not None:
                viewport = compute_viewport(
                    self.resources.world_map.width,
                    self.resources.world_map.height,
                    inner_width,
                    inner_height,
                    center=selected_pos,
                )
                self.state.camera_origin = (viewport.x, viewport.y)
            else:
                viewport = compute_viewport(
                    self.resources.world_map.width,
                    self.resources.world_map.height,
                    inner_width,
                    inner_height,
                    origin=self.state.camera_origin,
                )
                self.state.camera_origin = (viewport.x, viewport.y)

        lines = render_map_lines(
            self.resources.world_map,
            objects=self.resources.objects,
            agents=agents,
            selected_agent_id=self.state.selected_agent_id,
            viewport=viewport,
            room_areas=self.resources.room_bounds,
        )
        map_render = Align.center(Group(*lines), vertical="middle")
        renderable = Panel(map_render, title="World", padding=(0, 0))
        offset_x = 1 + max(0, (inner_width - viewport.width) // 2)
        offset_y = 1 + max(0, (inner_height - viewport.height) // 2)
        return MapRenderResult(
            renderable=renderable,
            viewport=viewport,
            map_width=viewport.width,
            map_height=viewport.height,
            offset_x=offset_x,
            offset_y=offset_y,
        )

    def _status_text(self) -> str:
        return ""


class MainViewerScreen(BaseViewerScreen):
    BINDINGS = [
        ("space", "toggle_pause", "Pause"),
        ("q", "quit", "Quit"),
        ("f", "follow", "Follow"),
        ("up", "pan_up", "Pan up"),
        ("down", "pan_down", "Pan down"),
        ("left", "pan_left", "Pan left"),
        ("right", "pan_right", "Pan right"),
    ]

    def __init__(
        self,
        payloads: Iterable[TickPayload],
        *,
        config: WorldConfig | None = None,
        base_dir: Path | None = None,
        tick_delay: float = 0.2,
    ) -> None:
        resources = _load_viewer_resources(config=config, base_dir=base_dir)
        super().__init__(resources=resources)
        self._payloads = iter(payloads)
        self._tick_delay = tick_delay
        self._paused = False
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None

    def on_mount(self) -> None:
        super().on_mount()
        self._start_worker()

    def on_unmount(self) -> None:
        self._stop_event.set()

    def _start_worker(self) -> None:
        self._worker = threading.Thread(target=self._payload_loop, daemon=True)
        self._worker.start()

    def _payload_loop(self) -> None:
        for payload in self._payloads:
            if self._stop_event.is_set():
                break
            while self._paused and not self._stop_event.is_set():
                time.sleep(0.05)
            if self._stop_event.is_set():
                break
            self.app.call_from_thread(self._accept_payload, payload)
            time.sleep(self._tick_delay)

    def _accept_payload(self, payload: TickPayload) -> None:
        self.resources = _maybe_reload_resources(self.resources, self.state)
        self._update_payload(payload)

    def action_toggle_pause(self) -> None:
        self._paused = not self._paused
        self._refresh_ui()

    def action_quit(self) -> None:
        self.app.exit()

    def action_follow(self) -> None:
        self.state.camera_mode = "follow"
        self._refresh_ui()

    def _pan(self, direction: str) -> None:
        self.state.camera_mode = "pan"
        self.state.camera_origin = _pan_origin(
            self.state.camera_origin,
            direction,
            self.resources.world_map.width,
            self.resources.world_map.height,
        )
        self._refresh_ui()

    def action_pan_up(self) -> None:
        self._pan("UP")

    def action_pan_down(self) -> None:
        self._pan("DOWN")

    def action_pan_left(self) -> None:
        self._pan("LEFT")

    def action_pan_right(self) -> None:
        self._pan("RIGHT")

    def _status_text(self) -> str:
        label = "paused" if self._paused else "live"
        return (
            "Main controls: space=pause | q=quit | f=follow | arrows=pan | "
            "[/]=cycle | 1-9=select | "
            + _reload_label(self.state.last_reload_at)
            + " | status="
            + label
        )


def run_main_viewer(
    payloads: Iterable[TickPayload],
    *,
    config: WorldConfig | None = None,
    base_dir: Path | None = None,
    tick_delay: float = 0.2,
) -> None:
    app = LatticevilleApp(
        MainViewerScreen(
            payloads,
            config=config,
            base_dir=base_dir,
            tick_delay=tick_delay,
        ),
        title="Latticeville",
    )
    app.run()


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

    if (
        map_width >= resources.world_map.width
        and map_height >= resources.world_map.height
    ):
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
        room_areas=resources.room_bounds,
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
    base_dir = base_dir or WorldPaths().base_dir
    paths = WorldPaths(base_dir=base_dir)
    config = config or load_world_config(paths=paths)
    map_path = base_dir / config.map_file
    world_map = _load_world_map(map_path)
    objects = {
        obj.id: ObjectState(
            object_id=obj.id,
            name=obj.name,
            room_id=obj.room_id or "",
            symbol=obj.symbol,
            position=obj.position,
            color=obj.color,
        )
        for obj in config.objects
    }
    room_bounds = [room.bounds for room in config.rooms]
    return ViewerResources(
        config=config,
        world_map=world_map,
        objects=objects,
        room_bounds=room_bounds,
        world_json_path=paths.world_json,
        map_path=map_path,
        world_json_mtime=_path_mtime(paths.world_json),
        map_mtime=_path_mtime(map_path),
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
            f"Plan [{level}] ({time_window} @ {location}): {_truncate(description, 70)}"
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
    return (
        _clamp(origin[0] + dx, 0, max(0, width - 1)),
        _clamp(origin[1] + dy, 0, max(0, height - 1)),
    )


def _maybe_reload_resources(
    resources: ViewerResources, state: MainViewerState
) -> ViewerResources:
    world_json_mtime = _path_mtime(resources.world_json_path)
    map_mtime = _path_mtime(resources.map_path)
    if (
        world_json_mtime == resources.world_json_mtime
        and map_mtime == resources.map_mtime
    ):
        return resources
    try:
        new_resources = _load_viewer_resources(
            config=None, base_dir=resources.world_json_path.parent
        )
    except FileNotFoundError:
        return resources
    state.last_reload_at = time.time()
    return new_resources


def _path_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return None


def _reload_label(last_reload_at: float | None) -> str:
    if last_reload_at is None:
        return "reload: -"
    stamp = time.strftime("%H:%M:%S", time.localtime(last_reload_at))
    return f"reload: {stamp}"


def _cycle(agent_ids: list[str], current: str | None, delta: int) -> str:
    if current not in agent_ids:
        return agent_ids[0]
    index = agent_ids.index(current)
    return agent_ids[(index + delta) % len(agent_ids)]


def map_character_index(agents: list[str], index: int) -> str | None:
    if index < 0 or index >= len(agents):
        return None
    return agents[index]


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


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))
