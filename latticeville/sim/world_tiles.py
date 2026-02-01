"""Shared tile definitions for world maps."""

from __future__ import annotations

from latticeville.sim.world_state import WorldMap

WALKABLE_TILES: set[str] = {
    ".",
    ",",
    ";",
    ":",
    "+",
    "=",
}


def is_walkable(world_map: WorldMap, x: int, y: int) -> bool:
    if x < 0 or y < 0 or y >= world_map.height or x >= world_map.width:
        return False
    return world_map.lines[y][x] in WALKABLE_TILES
