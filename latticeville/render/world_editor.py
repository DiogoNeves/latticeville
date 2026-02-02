"""World map editor for defining room bounds."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from rich.align import Align
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.events import Key
from textual.screen import Screen
from textual.widgets import Static, Tree
from textual.containers import Horizontal, Vertical

from latticeville.render.textual_app import LatticevilleApp
from latticeville.render.textual_widgets import MapClicked, MapRenderResult, MapWidget
from latticeville.render.world_map import (
    AGENT_STYLE,
    OBJECT_STYLE,
    ROOM_BORDER_STYLE,
    TILE_STYLES,
    compute_viewport,
    render_map_lines,
)
from latticeville.sim.world_loader import WorldConfig, WorldPaths, load_world_config
from latticeville.sim.world_state import Bounds, ObjectState, WorldMap
from latticeville.sim.world_tiles import is_walkable


LEFT_WIDTH = 44
RIGHT_WIDTH = 36
OBJECT_COLORS = [
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
    "bright_yellow",
    "bright_blue",
    "bright_magenta",
    "bright_cyan",
]


@dataclass
class EditorState:
    cursor: tuple[int, int] = (1, 1)
    selection_start: tuple[int, int] | None = None
    selection_end: tuple[int, int] | None = None
    rooms: list[RoomDef] = field(default_factory=list)
    should_exit: bool = False
    last_message: str = ""
    last_reload_at: float | None = None
    paint_enabled: bool = False
    brush: str | None = None
    input_mode: str | None = None
    input_buffer: str = ""
    pending_object_name: str | None = None
    pending_object_symbol: str | None = None
    pending_object_id: str | None = None
    unsaved_rooms: bool = False
    tree_dirty: bool = True


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


class WorldEditorScreen(Screen):
    CSS = """
    Screen {
        layout: vertical;
    }
    #world-tree {
        border: tall $accent;
    }
    #main {
        layout: horizontal;
        height: 1fr;
    }
    #center-pane {
        layout: vertical;
        width: 1fr;
    }
    #selection-bar {
        height: 3;
    }
    #status-bar {
        height: 3;
    }
    """

    BINDINGS = [
        ("up", "cursor_up", "Move up"),
        ("down", "cursor_down", "Move down"),
        ("left", "cursor_left", "Move left"),
        ("right", "cursor_right", "Move right"),
        ("t", "set_top_left", "Set top-left"),
        ("b", "set_bottom_right", "Set bottom-right"),
        ("s", "save", "Save"),
        ("space", "toggle_paint", "Paint"),
        ("c", "clear_paint", "Clear paint"),
        ("delete", "erase", "Erase"),
        ("o", "create_object", "Object"),
        ("q", "quit", "Quit"),
        ("ctrl+c", "force_quit", "Force quit"),
    ]

    def __init__(self, *, base_dir: Path | None = None) -> None:
        super().__init__()
        self._base_dir = base_dir
        self.resources = _load_editor_resources(base_dir=base_dir)
        self.state = EditorState(
            cursor=(1, 1),
            rooms=[
                RoomDef(room.id, room.name, room.bounds)
                for room in self.resources.config.rooms
            ],
        )
        self._world_tree: Tree | None = None
        self._selection_bar: Static | None = None
        self._editor_panel: Static | None = None
        self._status_bar: Static | None = None
        self._map_widget: MapWidget | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="root"):
            with Horizontal(id="main"):
                yield Tree("World", id="world-tree")
                with Vertical(id="center-pane"):
                    yield Static(id="selection-bar")
                    yield MapWidget(
                        self._render_map,
                        emit_clicks=True,
                        id="world-map",
                    )
                yield Static(id="editor-panel")
            yield Static(id="status-bar")

    def on_mount(self) -> None:
        self._world_tree = self.query_one("#world-tree", Tree)
        self._selection_bar = self.query_one("#selection-bar", Static)
        self._editor_panel = self.query_one("#editor-panel", Static)
        self._status_bar = self.query_one("#status-bar", Static)
        self._map_widget = self.query_one(MapWidget)
        self._world_tree.styles.width = LEFT_WIDTH
        self._world_tree.can_focus = False
        self._world_tree.show_root = True
        self._world_tree.border_title = "World Tree"
        self._editor_panel.styles.width = RIGHT_WIDTH
        self._refresh_ui()
        self.set_interval(0.15, self._tick)

    def _tick(self) -> None:
        refreshed = _maybe_reload_resources(self.state, self.resources)
        if refreshed is not self.resources:
            self.resources = refreshed
            self.state.tree_dirty = True
            self._refresh_ui()

    def _refresh_ui(self) -> None:
        if self._world_tree and self.state.tree_dirty:
            _populate_world_tree(self._world_tree, self.state, self.resources)
            self.state.tree_dirty = False
        if self._selection_bar:
            self._selection_bar.update(
                Panel(_selection_summary(self.state, self.resources), title="Selection")
            )
        if self._editor_panel:
            self._editor_panel.update(
                Panel(_render_editor_panel(self.state), title="Editor")
            )
        if self._status_bar:
            self._status_bar.update(_render_status_bar(self.state))
        if self._map_widget:
            self._map_widget.refresh()

    def _render_map(self, size, content_size) -> MapRenderResult:
        inner_width = max(1, content_size.width - 2)
        inner_height = max(1, content_size.height - 2)
        viewport = compute_viewport(
            self.resources.world_map.width,
            self.resources.world_map.height,
            inner_width,
            inner_height,
            center=self.state.cursor,
        )
        selection = _selection_bounds(self.state)
        room_bounds = [room.bounds for room in self.state.rooms]
        characters = _character_positions(self.resources, self.state.rooms)
        lines = render_map_lines(
            self.resources.world_map,
            objects=self.resources.objects,
            agents=characters,
            selected_agent_id=None,
            viewport=viewport,
            rooms=room_bounds,
            room_areas=room_bounds,
            selection=selection,
            cursor=self.state.cursor,
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

    def on_map_clicked(self, message: MapClicked) -> None:
        self.state.cursor = message.world_point
        self._refresh_ui()

    def on_key(self, event: Key) -> None:
        if self.state.input_mode:
            if event.key == "ctrl+c":
                _handle_text_input(self.state, self.resources, "ESC")
            else:
                _handle_text_input(self.state, self.resources, _key_from_event(event))
            self._refresh_ui()
            event.stop()
            return
        if event.character and _is_paint_brush(event.character):
            self.state.brush = event.character
            self.state.paint_enabled = True
            self.state.last_message = f"Brush: {event.character}"
            self._refresh_ui()
            event.stop()
            return
        if event.key == "backspace":
            self.action_erase()
            event.stop()

    def action_cursor_up(self) -> None:
        self._move_cursor("UP")

    def action_cursor_down(self) -> None:
        self._move_cursor("DOWN")

    def action_cursor_left(self) -> None:
        self._move_cursor("LEFT")

    def action_cursor_right(self) -> None:
        self._move_cursor("RIGHT")

    def _move_cursor(self, direction: str) -> None:
        if self.state.input_mode:
            return
        self.state.cursor = _move_cursor(
            self.state.cursor, direction, self.resources.world_map
        )
        if self.state.paint_enabled and self.state.brush:
            _apply_brush(self.resources, self.state.cursor, self.state.brush)
        self._refresh_ui()

    def action_set_top_left(self) -> None:
        if self.state.input_mode:
            return
        self.state.selection_start = self.state.cursor
        self.state.last_message = "Top-left set."
        self._refresh_ui()

    def action_set_bottom_right(self) -> None:
        if self.state.input_mode:
            return
        self.state.selection_end = self.state.cursor
        _maybe_commit_selection(self.state, self.resources)
        self.state.tree_dirty = True
        self._refresh_ui()

    def action_save(self) -> None:
        if self.state.input_mode:
            return
        _save_rooms(self.state, self.resources)
        self._refresh_ui()

    def action_toggle_paint(self) -> None:
        if self.state.input_mode:
            return
        obj = _object_for_point(self.resources.objects, self.state.cursor)
        if obj:
            self.state.input_mode = "object_color_edit"
            self.state.input_buffer = ""
            self.state.pending_object_id = obj.object_id
            self.state.last_message = f"Edit color for {obj.name}."
            self._refresh_ui()
            return
        if self.state.brush:
            self.state.paint_enabled = not self.state.paint_enabled
            self.state.last_message = (
                "Paint on." if self.state.paint_enabled else "Paint off."
            )
        self._refresh_ui()

    def action_clear_paint(self) -> None:
        if self.state.input_mode:
            return
        self.state.paint_enabled = False
        self.state.brush = None
        self.state.input_mode = None
        self.state.input_buffer = ""
        self.state.pending_object_name = None
        self.state.pending_object_symbol = None
        self.state.pending_object_id = None
        self.state.last_message = "Paint cleared."
        self._refresh_ui()

    def action_erase(self) -> None:
        if self.state.input_mode:
            return
        _erase_tile(self.state, self.resources)
        self.state.tree_dirty = True
        self._refresh_ui()

    def action_create_object(self) -> None:
        if self.state.input_mode:
            return
        self.state.input_mode = "object_name"
        self.state.input_buffer = ""
        self.state.pending_object_name = None
        self.state.pending_object_symbol = None
        self.state.pending_object_id = None
        self.state.last_message = "Enter object name."
        self._refresh_ui()

    def action_quit(self) -> None:
        if self.state.unsaved_rooms:
            self.state.last_message = "Unsaved rooms. Press Ctrl+C to quit."
            self._refresh_ui()
            return
        self.app.exit()

    def action_force_quit(self) -> None:
        if self.state.unsaved_rooms:
            self.app.exit()


def run_world_editor(*, base_dir: Path | None = None) -> None:
    app = LatticevilleApp(
        WorldEditorScreen(base_dir=base_dir), title="Latticeville Editor"
    )
    app.run()


def _populate_world_tree(
    tree: Tree, state: EditorState, resources: EditorResources
) -> None:
    wall_style = TILE_STYLES.get("#", "grey50")
    room_style = ROOM_BORDER_STYLE
    tree.reset(Text("World", style=wall_style))
    root = tree.root
    objects_by_room: dict[str, list[ObjectState]] = {}
    for obj in resources.objects.values():
        objects_by_room.setdefault(obj.room_id or "", []).append(obj)
    characters_by_room: dict[str, list] = {}
    for char in resources.config.characters:
        characters_by_room.setdefault(char.start_room_id, []).append(char)

    for room in state.rooms:
        bounds = room.bounds
        room_label = Text(
            f"{room.name} {bounds.x},{bounds.y} {bounds.width}x{bounds.height} "
            f"({room.room_id})",
            style=room_style,
        )
        room_node = root.add(room_label)
        for obj in sorted(
            objects_by_room.get(room.room_id, []), key=lambda o: o.object_id
        ):
            object_label = Text()
            object_label.append(f"{obj.name} ")
            object_label.append(
                f"{obj.position[0]},{obj.position[1]} ({obj.object_id}) "
            )
            object_label.append(obj.symbol, style=obj.color or OBJECT_STYLE)
            room_node.add(object_label)
        for char in sorted(
            characters_by_room.get(room.room_id, []), key=lambda c: c.id
        ):
            character_label = Text()
            character_label.append(f"{char.name} ")
            character_label.append(f"({char.id}) ")
            character_label.append(char.symbol, style=AGENT_STYLE)
            room_node.add(character_label)

    if not state.rooms:
        root.add("No rooms defined")
    root.expand()


def _render_editor_panel(state: EditorState) -> RenderableType:
    table = Table(show_header=False)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Cursor", f"{state.cursor[0]}, {state.cursor[1]}")
    table.add_row("Paint", "on" if state.paint_enabled else "off")
    table.add_row("Brush", state.brush or "-")
    if state.selection_start:
        table.add_row(
            "Top-left", f"{state.selection_start[0]}, {state.selection_start[1]}"
        )
    else:
        table.add_row("Top-left", "-")
    if state.selection_end:
        table.add_row(
            "Bottom-right", f"{state.selection_end[0]}, {state.selection_end[1]}"
        )
    else:
        table.add_row("Bottom-right", "-")
    if state.input_mode:
        if state.input_mode == "object_name":
            table.add_row("Object name", state.input_buffer or "…")
        elif state.input_mode == "object_char":
            table.add_row("Object char", state.input_buffer or "…")
        elif state.input_mode == "object_color":
            table.add_row("Object color", state.input_buffer or "…")
            table.add_row("Colors", _color_options_label())
        elif state.input_mode == "object_color_edit":
            table.add_row("Edit color", state.input_buffer or "…")
            table.add_row("Colors", _color_options_label())
    if state.pending_object_name and state.input_mode != "object_name":
        table.add_row("Pending obj", state.pending_object_name)
    if state.last_message:
        table.add_row("Note", state.last_message)
    return table


def _render_status_bar(state: EditorState) -> Panel:
    text = Text(
        "Editor: arrows=move | t=set top-left | b=set bottom-right | s=save | "
        "space=paint | c=clear paint | del=erase | o=object | q=quit | "
        + _reload_label(state.last_reload_at),
        style="bold",
    )
    return Panel(text, padding=(0, 1))


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


def _maybe_commit_selection(state: EditorState, resources: EditorResources) -> None:
    if state.selection_start is None or state.selection_end is None:
        return
    bounds = _normalize_bounds(state.selection_start, state.selection_end)
    room_id = _next_room_id(state.rooms)
    name = f"Room {len(state.rooms) + 1}"
    state.rooms.append(RoomDef(room_id=room_id, name=name, bounds=bounds))
    _apply_room_to_map(resources, bounds)
    state.unsaved_rooms = True
    state.tree_dirty = True
    state.selection_start = None
    state.selection_end = None
    state.last_message = f"Added {name} and fenced map."


def _normalize_bounds(start: tuple[int, int], end: tuple[int, int]) -> Bounds:
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
    _update_resource_mtime(resources, "world_json_mtime")
    state.unsaved_rooms = False
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
            color=obj.color,
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
        new_resources = _load_editor_resources(
            base_dir=resources.world_json_path.parent
        )
    except FileNotFoundError as exc:
        state.last_message = f"Reload failed: {exc}"
        return resources

    state.rooms = [
        RoomDef(room.id, room.name, room.bounds) for room in new_resources.config.rooms
    ]
    state.unsaved_rooms = False
    state.cursor = _clamp_point(state.cursor, new_resources.world_map)
    if state.selection_start:
        state.selection_start = _clamp_point(
            state.selection_start, new_resources.world_map
        )
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


def _update_resource_mtime(resources: EditorResources, field_name: str) -> None:
    if field_name == "world_json_mtime":
        mtime = _path_mtime(resources.world_json_path)
    elif field_name == "map_mtime":
        mtime = _path_mtime(resources.map_path)
    else:
        return
    object.__setattr__(resources, field_name, mtime)


def _apply_room_to_map(resources: EditorResources, bounds: Bounds) -> None:
    grid = [list(line) for line in resources.world_map.lines]
    width = resources.world_map.width
    height = resources.world_map.height
    x0 = max(0, bounds.x)
    y0 = max(0, bounds.y)
    x1 = min(width - 1, bounds.x + bounds.width - 1)
    y1 = min(height - 1, bounds.y + bounds.height - 1)

    for x in range(x0, x1 + 1):
        if 0 <= y0 < height:
            grid[y0][x] = "#"
        if 0 <= y1 < height:
            grid[y1][x] = "#"
    for y in range(y0, y1 + 1):
        if 0 <= x0 < width:
            grid[y][x0] = "#"
        if 0 <= x1 < width:
            grid[y][x1] = "#"

    for y in range(y0 + 1, y1):
        for x in range(x0 + 1, x1):
            grid[y][x] = "."

    updated = ["".join(row) for row in grid]
    resources.world_map.lines[:] = updated
    resources.map_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
    _update_resource_mtime(resources, "map_mtime")


def _apply_brush(
    resources: EditorResources, point: tuple[int, int], brush: str
) -> None:
    x, y = point
    if not (0 <= x < resources.world_map.width and 0 <= y < resources.world_map.height):
        return
    grid = [list(line) for line in resources.world_map.lines]
    grid[y][x] = brush
    updated = ["".join(row) for row in grid]
    resources.world_map.lines[:] = updated
    resources.map_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
    _update_resource_mtime(resources, "map_mtime")


def _erase_tile(state: EditorState, resources: EditorResources) -> None:
    x, y = state.cursor
    if not (0 <= x < resources.world_map.width and 0 <= y < resources.world_map.height):
        return
    obj = _object_for_point(resources.objects, state.cursor)
    if obj:
        _delete_object(resources, obj.object_id)
    current = resources.world_map.lines[y][x]
    if current == "#":
        replacement = " "
    else:
        room = _room_for_point(state.rooms, state.cursor)
        replacement = "." if room else ","
    _apply_brush(resources, state.cursor, replacement)
    state.last_message = "Tile cleared."


def _is_paint_brush(key: str) -> bool:
    return key in {"#", ".", ",", ";", ":", "-", "+", "=", "~", "^"}


def _handle_text_input(
    state: EditorState, resources: EditorResources, key: str
) -> None:
    if key in {"ENTER"}:
        if state.input_mode == "object_name":
            name = state.input_buffer.strip()
            if not name:
                state.last_message = "Object name required."
                return
            state.pending_object_name = name
            state.input_mode = "object_char"
            state.input_buffer = ""
            state.last_message = "Enter object character."
            return
        if state.input_mode == "object_char":
            symbol = state.input_buffer.strip()[:1]
            if not symbol:
                state.last_message = "Object character required."
                return
            state.pending_object_symbol = symbol
            state.input_mode = "object_color"
            state.input_buffer = ""
            state.last_message = "Pick object color."
            return
        if state.input_mode == "object_color":
            color = _color_from_buffer(state.input_buffer)
            if color is None:
                state.last_message = "Pick a valid color number."
                return
            _create_object_at_cursor(
                state, resources, state.pending_object_symbol or "*", color
            )
            state.tree_dirty = True
            state.input_mode = None
            state.input_buffer = ""
            state.pending_object_name = None
            state.pending_object_symbol = None
            return
        if state.input_mode == "object_color_edit":
            color = _color_from_buffer(state.input_buffer)
            if color is None:
                state.last_message = "Pick a valid color number."
                return
            if state.pending_object_id:
                _update_object_color(resources, state.pending_object_id, color)
                state.last_message = "Object color updated."
                state.tree_dirty = True
            state.input_mode = None
            state.input_buffer = ""
            state.pending_object_id = None
            return
    if key in {"BACKSPACE"}:
        state.input_buffer = state.input_buffer[:-1]
        return
    if key in {"ESC"}:
        state.input_mode = None
        state.input_buffer = ""
        state.pending_object_name = None
        state.pending_object_symbol = None
        state.pending_object_id = None
        state.last_message = "Input cancelled."
        return
    if len(key) == 1 and key.isprintable():
        state.input_buffer += key


def _create_object_at_cursor(
    state: EditorState, resources: EditorResources, symbol: str, color: str | None
) -> None:
    name = state.pending_object_name or "Object"
    obj_id = _slugify(name)
    existing_ids = {obj.object_id for obj in resources.objects.values()}
    obj_id = _dedupe_id(obj_id, existing_ids)
    room = _room_for_point(state.rooms, state.cursor)
    room_id = room.room_id if room else None

    payload = json.loads(resources.world_json_path.read_text(encoding="utf-8"))
    objects = payload.get("objects", [])
    objects.append(
        {
            "id": obj_id,
            "name": name,
            "room_id": room_id,
            "symbol": symbol,
            "color": color,
            "position": {"x": state.cursor[0], "y": state.cursor[1]},
        }
    )
    payload["objects"] = objects
    resources.world_json_path.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    resources.objects[obj_id] = ObjectState(
        object_id=obj_id,
        name=name,
        room_id=room_id or "",
        symbol=symbol,
        position=state.cursor,
        color=color,
    )
    _update_resource_mtime(resources, "world_json_mtime")
    state.tree_dirty = True
    state.last_message = f"Placed {name}."


def _update_object_color(
    resources: EditorResources, object_id: str, color: str
) -> None:
    payload = json.loads(resources.world_json_path.read_text(encoding="utf-8"))
    objects = payload.get("objects", [])
    for obj in objects:
        if obj.get("id") == object_id:
            obj["color"] = color
            break
    payload["objects"] = objects
    resources.world_json_path.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    if object_id in resources.objects:
        obj_state = resources.objects[object_id]
        resources.objects[object_id] = ObjectState(
            object_id=obj_state.object_id,
            name=obj_state.name,
            room_id=obj_state.room_id,
            symbol=obj_state.symbol,
            position=obj_state.position,
            color=color,
        )
    _update_resource_mtime(resources, "world_json_mtime")


def _delete_object(resources: EditorResources, object_id: str) -> None:
    payload = json.loads(resources.world_json_path.read_text(encoding="utf-8"))
    objects = payload.get("objects", [])
    payload["objects"] = [obj for obj in objects if obj.get("id") != object_id]
    resources.world_json_path.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    resources.objects.pop(object_id, None)
    _update_resource_mtime(resources, "world_json_mtime")


def _slugify(name: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_")
    return safe or "object"


def _dedupe_id(base: str, existing: set[str]) -> str:
    if base not in existing:
        return base
    index = 2
    while f"{base}_{index}" in existing:
        index += 1
    return f"{base}_{index}"


def _color_options_label() -> str:
    return " ".join(f"{index + 1}={color}" for index, color in enumerate(OBJECT_COLORS))


def _color_from_buffer(buffer: str) -> str | None:
    text = buffer.strip()
    if not text:
        return None
    if text.isdigit():
        index = int(text) - 1
        if 0 <= index < len(OBJECT_COLORS):
            return OBJECT_COLORS[index]
        return None
    for color in OBJECT_COLORS:
        if text.lower() == color.lower():
            return color
    return None


def _key_from_event(event: Key) -> str:
    key = event.key
    if key in {"enter", "return"}:
        return "ENTER"
    if key == "backspace":
        return "BACKSPACE"
    if key == "delete":
        return "DELETE"
    if event.character:
        return event.character
    return key.upper()


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


def _room_for_point(rooms: list[RoomDef], point: tuple[int, int]) -> RoomDef | None:
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
        positions[char.id] = _find_spawn_position(resources.world_map, bounds, blocked)
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
