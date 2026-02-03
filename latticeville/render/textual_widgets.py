"""Shared Textual widgets for map rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from rich.console import RenderableType
from textual.events import Click
from textual.geometry import Size
from textual.message import Message
from textual.widget import Widget

from latticeville.render.world_map import Viewport


@dataclass(frozen=True)
class MapRenderResult:
    renderable: RenderableType
    viewport: Viewport
    map_width: int
    map_height: int
    offset_x: int
    offset_y: int


class MapClicked(Message):
    """Message emitted when a map click resolves to world coordinates."""

    def __init__(self, *, world_point: tuple[int, int]) -> None:
        super().__init__()
        self.world_point = world_point


class MapWidget(Widget):
    """Render a world map and optionally emit click events."""

    def __init__(
        self,
        render_map: Callable[[Size, Size], MapRenderResult],
        *,
        emit_clicks: bool = False,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._render_map = render_map
        self._emit_clicks = emit_clicks
        self._viewport: Viewport | None = None
        self._map_width = 0
        self._map_height = 0
        self._offset_x = 0
        self._offset_y = 0

    def render(self) -> RenderableType:
        result = self._render_map(self.size, self.content_size)
        self._viewport = result.viewport
        self._map_width = result.map_width
        self._map_height = result.map_height
        self._offset_x = result.offset_x
        self._offset_y = result.offset_y
        return result.renderable

    def on_click(self, event: Click) -> None:
        if not self._emit_clicks or self._viewport is None:
            return
        offset = event.get_content_offset(self)
        if offset is None:
            return
        x, y = offset
        if not (
            self._offset_x <= x < self._offset_x + self._map_width
            and self._offset_y <= y < self._offset_y + self._map_height
        ):
            return
        world_x = self._viewport.x + (x - self._offset_x)
        world_y = self._viewport.y + (y - self._offset_y)
        self.post_message(MapClicked(world_point=(world_x, world_y)))
