"""Shared helpers for rendering the world map and viewports."""

from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text

from latticeville.sim.world_state import Bounds, ObjectState, WorldMap


TILE_STYLES = {
    "#": "bright_magenta",
    ".": "grey70",
    ",": "green3",
    ";": "yellow",
    ":": "yellow3",
    "+": "yellow",
    "=": "yellow",
    "~": "blue",
    "^": "red",
    "-": "blue",
}

SAND_STYLE = "yellow"

OBJECT_STYLE = "bright_yellow"
ROOM_BORDER_STYLE = "bright_magenta"
SELECTION_STYLE = "bold bright_green"
CURSOR_STYLE = "reverse"
AGENT_STYLE = "bright_cyan"
SELECTED_AGENT_STYLE = "bold bright_green"


@dataclass(frozen=True)
class Viewport:
    x: int
    y: int
    width: int
    height: int


def compute_viewport(
    world_width: int,
    world_height: int,
    view_width: int,
    view_height: int,
    *,
    center: tuple[int, int] | None = None,
    origin: tuple[int, int] | None = None,
) -> Viewport:
    view_width = max(1, min(world_width, view_width))
    view_height = max(1, min(world_height, view_height))

    if center is not None:
        origin_x = center[0] - view_width // 2
        origin_y = center[1] - view_height // 2
    elif origin is not None:
        origin_x, origin_y = origin
    else:
        origin_x, origin_y = 0, 0

    origin_x = _clamp(origin_x, 0, max(0, world_width - view_width))
    origin_y = _clamp(origin_y, 0, max(0, world_height - view_height))

    return Viewport(x=origin_x, y=origin_y, width=view_width, height=view_height)


def render_map_lines(
    world_map: WorldMap,
    *,
    objects: dict[str, ObjectState],
    agents: dict[str, tuple[int, int]],
    selected_agent_id: str | None,
    viewport: Viewport,
    rooms: list[Bounds] | None = None,
    room_areas: list[Bounds] | None = None,
    selection: Bounds | None = None,
    cursor: tuple[int, int] | None = None,
) -> list[Text]:
    grid = [list(line) for line in world_map.lines]
    styles = [
        [TILE_STYLES.get(ch, "grey70") for ch in row] for row in grid
    ]
    _apply_flower_styles(grid, styles)
    if room_areas:
        _apply_outside_floor_styles(grid, styles, room_areas)

    for obj in objects.values():
        x, y = obj.position
        if 0 <= y < world_map.height and 0 <= x < world_map.width:
            grid[y][x] = obj.symbol
            styles[y][x] = OBJECT_STYLE

    if rooms:
        for bounds in rooms:
            _apply_bounds_style(styles, bounds, ROOM_BORDER_STYLE)

    if selection:
        _apply_bounds_style(styles, selection, SELECTION_STYLE)

    for agent_id, (x, y) in agents.items():
        if 0 <= y < world_map.height and 0 <= x < world_map.width:
            grid[y][x] = "@"
            styles[y][x] = (
                SELECTED_AGENT_STYLE
                if agent_id == selected_agent_id
                else AGENT_STYLE
            )

    _apply_boundary_styles(grid, styles)

    if cursor:
        cx, cy = cursor
        if 0 <= cy < world_map.height and 0 <= cx < world_map.width:
            styles[cy][cx] = CURSOR_STYLE

    lines: list[Text] = []
    for y in range(viewport.y, viewport.y + viewport.height):
        line = Text()
        row = grid[y]
        row_styles = styles[y]
        for x in range(viewport.x, viewport.x + viewport.width):
            line.append(row[x], style=row_styles[x])
        lines.append(line)
    return lines


def _apply_bounds_style(styles: list[list[str]], bounds: Bounds, style: str) -> None:
    x0 = bounds.x
    y0 = bounds.y
    x1 = bounds.x + bounds.width - 1
    y1 = bounds.y + bounds.height - 1
    height = len(styles)
    width = len(styles[0]) if height else 0

    for x in range(x0, x1 + 1):
        if 0 <= y0 < height and 0 <= x < width:
            styles[y0][x] = style
        if 0 <= y1 < height and 0 <= x < width:
            styles[y1][x] = style
    for y in range(y0, y1 + 1):
        if 0 <= y < height and 0 <= x0 < width:
            styles[y][x0] = style
        if 0 <= y < height and 0 <= x1 < width:
            styles[y][x1] = style


def _apply_boundary_styles(grid: list[list[str]], styles: list[list[str]]) -> None:
    height = len(grid)
    width = len(grid[0]) if height else 0
    if not height or not width:
        return
    for x in range(width):
        if grid[0][x] == "#":
            styles[0][x] = "grey50"
        if grid[height - 1][x] == "#":
            styles[height - 1][x] = "grey50"
    for y in range(height):
        if grid[y][0] == "#":
            styles[y][0] = "grey50"
        if grid[y][width - 1] == "#":
            styles[y][width - 1] = "grey50"


def _apply_flower_styles(grid: list[list[str]], styles: list[list[str]]) -> None:
    palette = ["yellow", "bright_magenta", "white"]
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch != ";":
                continue
            styles[y][x] = palette[(x + y) % len(palette)]


def _apply_outside_floor_styles(
    grid: list[list[str]], styles: list[list[str]], rooms: list[Bounds]
) -> None:
    height = len(grid)
    width = len(grid[0]) if height else 0
    if not height or not width:
        return
    inside = [[False] * width for _ in range(height)]
    for bounds in rooms:
        x0 = max(0, bounds.x)
        y0 = max(0, bounds.y)
        x1 = min(width - 1, bounds.x + bounds.width - 1)
        y1 = min(height - 1, bounds.y + bounds.height - 1)
        for y in range(y0, y1 + 1):
            row = inside[y]
            for x in range(x0, x1 + 1):
                row[x] = True
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch == "." and not inside[y][x]:
                styles[y][x] = SAND_STYLE


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))
