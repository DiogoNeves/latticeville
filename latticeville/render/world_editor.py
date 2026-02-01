"""World map editor for defining room bounds."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from rich.align import Align
from rich.console import Console, Group, RenderableType
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich.text import Text
from rich.live import Live

from latticeville.render.terminal_input import raw_terminal, read_key
from latticeville.render.world_map import (
    AGENT_STYLE,
    OBJECT_STYLE,
    TILE_STYLES,
    compute_viewport,
    render_map_lines,
)
from latticeville.sim.world_loader import WorldConfig, WorldPaths, load_world_config
from latticeville.sim.world_state import Bounds, ObjectState, WorldMap
from latticeville.sim.world_tiles import is_walkable


LEFT_WIDTH = 44
RIGHT_WIDTH = 36


@dataclass
class EditorState:
    cursor: tuple[int, int] = (1, 1)
    selection_start: tuple[int, int] | None = None
    selection_end: tuple[int, int] | None = None
    rooms: list[RoomDef] = field(default_factory=list)
    should_exit: bool = False
    last_message: str = ""
    last_reload_at: float | None = None


@dataclass(frozen=True)
class RoomDef:
    room_id: str
    name: str
    bounds: Bounds


@dataclass(frozen=True)
class EditorResources:
    config: WorldConfig
    world_map: WorldMap
    objects: dict[str, ObjectState]
    world_json_path: Path
    map_path: Path
    world_json_mtime: float | None
    map_mtime: float | None


def run_world_editor(*, base_dir: Path | None = None) -> None:
    resources = _load_editor_resources(base_dir=base_dir)
    state = EditorState(
        cursor=(1, 1),
        rooms=[RoomDef(room.id, room.name, room.bounds) for room in resources.config.rooms],
    )
    console = Console()

    with raw_terminal():
        with Live(console=console, auto_refresh=False, screen=True) as live:
            try:
                while not state.should_exit:
                    resources = _maybe_reload_resources(state, resources)
                    _handle_input(state, resources)
                    renderable = _render_editor(state, resources, frame_size=console.size)
                    live.update(renderable, refresh=True)
                    time.sleep(0.03)
            except KeyboardInterrupt:
                state.should_exit = True


def _render_editor(
    state: EditorState, resources: EditorResources, *, frame_size
) -> RenderableType:
    map_width, map_height = _map_panel_size(frame_size)
    viewport = compute_viewport(
        resources.world_map.width,
        resources.world_map.height,
        map_width,
        map_height,
        center=state.cursor,
    )

    selection = _selection_bounds(state)
    room_bounds = [room.bounds for room in state.rooms]

    lines = render_map_lines(
        resources.world_map,
        objects=resources.objects,
        agents={},
        selected_agent_id=None,
        viewport=viewport,
        rooms=room_bounds,
        selection=selection,
        cursor=state.cursor,
    )
    map_panel = Align.center(Group(*lines), vertical="middle")

    left = _render_world_tree(state, resources)
    right = _render_editor_panel(state)
    center = _render_center_panel(state, resources, map_panel)

    layout = Layout()
    layout.split_row(
        Layout(Panel(left, title="World Tree"), size=LEFT_WIDTH),
        Layout(center, ratio=1),
        Layout(Panel(right, title="Editor"), size=RIGHT_WIDTH),
    )

    wrapper = Layout()
    wrapper.split_column(
        Layout(layout, ratio=1),
        Layout(_render_status_bar(state), size=3),
    )
    return wrapper


def _render_world_tree(
    state: EditorState, resources: EditorResources
) -> RenderableType:
    wall_style = TILE_STYLES.get("#", "grey50")
    tree = Tree(Text("World", style=wall_style), guide_style=wall_style)
    objects_by_room: dict[str, list[ObjectState]] = {}
    for obj in resources.objects.values():
        objects_by_room.setdefault(obj.room_id or "", []).append(obj)
    characters_by_room: dict[str, list] = {}
    for char in resources.config.characters:
        characters_by_room.setdefault(char.start_room_id, []).append(char)

    for room in state.rooms:
        bounds = room.bounds
        room_label = Text(
            f"{bounds.x},{bounds.y} {bounds.width}x{bounds.height} "
            f"{room.room_id} ({room.name})",
            style=wall_style,
        )
        room_node = tree.add(room_label)
        for obj in sorted(
            objects_by_room.get(room.room_id, []), key=lambda o: o.object_id
        ):
            object_label = Text()
            object_label.append(f"{obj.name} ")
            object_label.append(obj.symbol, style=OBJECT_STYLE)
            object_label.append(
                f" @ {obj.position[0]},{obj.position[1]} ({obj.object_id})"
            )
            room_node.add(object_label)
        for char in sorted(
            characters_by_room.get(room.room_id, []), key=lambda c: c.id
        ):
            character_label = Text()
            character_label.append(f"{char.name} ")
            character_label.append(char.symbol, style=AGENT_STYLE)
            character_label.append(f" ({char.id})")
            room_node.add(character_label)

    if not state.rooms:
        tree.add("No rooms defined")
    return tree


def _render_editor_panel(state: EditorState) -> RenderableType:
    table = Table(show_header=False)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Cursor", f"{state.cursor[0]}, {state.cursor[1]}")
    if state.selection_start:
        table.add_row("Top-left", f"{state.selection_start[0]}, {state.selection_start[1]}")
    else:
        table.add_row("Top-left", "-")
    if state.selection_end:
        table.add_row("Bottom-right", f"{state.selection_end[0]}, {state.selection_end[1]}")
    else:
        table.add_row("Bottom-right", "-")
    if state.last_message:
        table.add_row("Note", state.last_message)
    return table


def _render_status_bar(state: EditorState) -> Panel:
    text = Text(
        "Editor: arrows=move | t=set top-left | b=set bottom-right | s=save | "
        "c=clear | q=quit | "
        + _reload_label(state.last_reload_at),
        style="bold",
    )
    return Panel(text, padding=(0, 1))


def _handle_input(state: EditorState, resources: EditorResources) -> None:
    event = read_key()
    if not event:
        return
    if event.kind != "key":
        return
    key = event.key or ""

    if key in {"q", "Q"}:
        state.should_exit = True
        return
    if key in {"c", "C"}:
        state.selection_start = None
        state.selection_end = None
        state.last_message = "Selection cleared."
        return
    if key in {"s", "S"}:
        _save_rooms(state, resources)
        return
    if key in {"t", "T"}:
        state.selection_start = state.cursor
        state.last_message = "Top-left set."
        return
    if key in {"b", "B"}:
        state.selection_end = state.cursor
        _maybe_commit_selection(state)
        return

    if key in {"UP", "DOWN", "LEFT", "RIGHT"}:
        state.cursor = _move_cursor(state.cursor, key, resources.world_map)
        return


def _render_center_panel(
    state: EditorState, resources: EditorResources, map_panel: RenderableType
) -> Layout:
    selection = _selection_summary(state, resources)
    bar = Panel(selection, title="Selection", padding=(0, 1))
    layout = Layout()
    layout.split_column(
        Layout(bar, size=3),
        Layout(Panel(map_panel, title="World"), ratio=1),
    )
    return layout


def _move_cursor(
    cursor: tuple[int, int], key: str, world_map: WorldMap
) -> tuple[int, int]:
    x, y = cursor
    if key == "UP":
        y -= 1
    elif key == "DOWN":
        y += 1
    elif key == "LEFT":
        x -= 1
    elif key == "RIGHT":
        x += 1
    x = max(0, min(world_map.width - 1, x))
    y = max(0, min(world_map.height - 1, y))
    return (x, y)


def _maybe_commit_selection(state: EditorState) -> None:
    if state.selection_start is None or state.selection_end is None:
        return
    bounds = _normalize_bounds(state.selection_start, state.selection_end)
    room_id = _next_room_id(state.rooms)
    name = f"Room {len(state.rooms) + 1}"
    state.rooms.append(RoomDef(room_id=room_id, name=name, bounds=bounds))
    state.selection_start = None
    state.selection_end = None
    state.last_message = f"Added {name}."


def _normalize_bounds(
    start: tuple[int, int], end: tuple[int, int]
) -> Bounds:
    x0, y0 = start
    x1, y1 = end
    left = min(x0, x1)
    top = min(y0, y1)
    right = max(x0, x1)
    bottom = max(y0, y1)
    return Bounds(x=left, y=top, width=right - left + 1, height=bottom - top + 1)


def _selection_bounds(state: EditorState) -> Bounds | None:
    if state.selection_start and state.selection_end:
        return _normalize_bounds(state.selection_start, state.selection_end)
    if state.selection_start:
        x, y = state.selection_start
        return Bounds(x=x, y=y, width=1, height=1)
    return None


def _next_room_id(rooms: list[RoomDef]) -> str:
    index = len(rooms) + 1
    return f"room_{index:02d}"


def _save_rooms(state: EditorState, resources: EditorResources) -> None:
    payload = json.loads(resources.world_json_path.read_text(encoding="utf-8"))
    payload["rooms"] = [
        {
            "id": room.room_id,
            "name": room.name,
            "bounds": {
                "x": room.bounds.x,
                "y": room.bounds.y,
                "width": room.bounds.width,
                "height": room.bounds.height,
            },
        }
        for room in state.rooms
    ]
    resources.world_json_path.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    state.last_message = "Saved to world.json."


def _load_editor_resources(*, base_dir: Path | None) -> EditorResources:
    base_dir = base_dir or WorldPaths().base_dir
    paths = WorldPaths(base_dir=base_dir)
    config = load_world_config(paths=paths)
    world_json_path = paths.world_json
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
    return EditorResources(
        config=config,
        world_map=world_map,
        objects=objects,
        world_json_path=world_json_path,
        map_path=map_path,
        world_json_mtime=_path_mtime(world_json_path),
        map_mtime=_path_mtime(map_path),
    )


def _load_world_map(path: Path) -> WorldMap:
    lines = path.read_text(encoding="utf-8").splitlines()
    width = max((len(line) for line in lines), default=0)
    padded = [line.ljust(width) for line in lines]
    return WorldMap(lines=padded, width=width, height=len(padded))


def _map_panel_size(frame_size) -> tuple[int, int]:
    if frame_size is None:
        return (80, 24)
    width = max(10, frame_size.width - LEFT_WIDTH - RIGHT_WIDTH - 6)
    height = max(6, frame_size.height - 3)
    return (max(1, width - 2), max(1, height - 2))


def _maybe_reload_resources(
    state: EditorState, resources: EditorResources
) -> EditorResources:
    world_json_mtime = _path_mtime(resources.world_json_path)
    map_mtime = _path_mtime(resources.map_path)
    if (
        world_json_mtime == resources.world_json_mtime
        and map_mtime == resources.map_mtime
    ):
        return resources
    try:
        new_resources = _load_editor_resources(base_dir=resources.world_json_path.parent)
    except FileNotFoundError as exc:
        state.last_message = f"Reload failed: {exc}"
        return resources

    state.rooms = [
        RoomDef(room.id, room.name, room.bounds) for room in new_resources.config.rooms
    ]
    state.cursor = _clamp_point(state.cursor, new_resources.world_map)
    if state.selection_start:
        state.selection_start = _clamp_point(state.selection_start, new_resources.world_map)
    if state.selection_end:
        state.selection_end = _clamp_point(state.selection_end, new_resources.world_map)
    state.last_message = "Reloaded world files."
    state.last_reload_at = time.time()
    return new_resources


def _clamp_point(point: tuple[int, int], world_map: WorldMap) -> tuple[int, int]:
    x, y = point
    x = max(0, min(world_map.width - 1, x))
    y = max(0, min(world_map.height - 1, y))
    return (x, y)


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


def _selection_summary(state: EditorState, resources: EditorResources) -> Text:
    cursor = state.cursor
    room = _room_for_point(state.rooms, cursor)
    char = _character_for_point(resources, state.rooms, cursor)
    obj = _object_for_point(resources.objects, cursor) if char is None else None
    path_parts = ["World"]
    if room:
        path_parts.append(room.name)
    if char:
        path_parts.append(char.name)
    elif obj:
        path_parts.append(obj.name)
    path = " / ".join(path_parts)

    return Text(
        f"Cursor: {cursor[0]}, {cursor[1]} | Path: {path}",
        style="bold",
    )


def _room_for_point(
    rooms: list[RoomDef], point: tuple[int, int]
) -> RoomDef | None:
    x, y = point
    for room in rooms:
        bounds = room.bounds
        if (
            bounds.x <= x < bounds.x + bounds.width
            and bounds.y <= y < bounds.y + bounds.height
        ):
            return room
    return None


def _object_for_point(
    objects: dict[str, ObjectState], point: tuple[int, int]
) -> ObjectState | None:
    for obj in objects.values():
        if obj.position == point:
            return obj
    return None


def _character_for_point(
    resources: EditorResources, rooms: list[RoomDef], point: tuple[int, int]
):
    positions = _character_positions(resources, rooms)
    for char in resources.config.characters:
        if positions.get(char.id) == point:
            return char
    return None


def _character_positions(
    resources: EditorResources, rooms: list[RoomDef]
) -> dict[str, tuple[int, int]]:
    room_map = {room.room_id: room.bounds for room in rooms}
    blocked = {obj.position for obj in resources.objects.values()}
    positions: dict[str, tuple[int, int]] = {}
    for char in resources.config.characters:
        bounds = room_map.get(char.start_room_id)
        if bounds is None:
            continue
        positions[char.id] = _find_spawn_position(
            resources.world_map, bounds, blocked
        )
    return positions


def _find_spawn_position(
    world_map: WorldMap, bounds: Bounds, blocked: set[tuple[int, int]]
) -> tuple[int, int]:
    for y in range(bounds.y + 1, bounds.y + bounds.height - 1):
        for x in range(bounds.x + 1, bounds.x + bounds.width - 1):
            if (x, y) in blocked:
                continue
            if _is_walkable(world_map, x, y):
                return (x, y)
    return (bounds.x + 1, bounds.y + 1)


def _is_walkable(world_map: WorldMap, x: int, y: int) -> bool:
    return is_walkable(world_map, x, y)
