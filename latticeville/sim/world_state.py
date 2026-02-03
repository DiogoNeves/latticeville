"""World and agent runtime state for the minimal sim loop."""

from __future__ import annotations

from dataclasses import dataclass, field

from latticeville.sim.contracts import WorldTree


@dataclass(frozen=True)
class Bounds:
    x: int
    y: int
    width: int
    height: int

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.width and self.y <= y < self.y + self.height


@dataclass(frozen=True)
class RoomState:
    room_id: str
    name: str
    bounds: Bounds


@dataclass(frozen=True)
class ObjectState:
    object_id: str
    name: str
    room_id: str
    symbol: str
    position: tuple[int, int]
    color: str | None = None


@dataclass(frozen=True)
class WorldMap:
    lines: list[str]
    width: int
    height: int


@dataclass
class AgentState:
    agent_id: str
    name: str
    location_id: str
    position: tuple[int, int]
    personality: str = ""
    path_remaining: list[tuple[int, int]] = field(default_factory=list)
    travel_origin: str | None = None
    travel_destination: str | None = None


@dataclass
class WorldState:
    world: WorldTree
    world_map: WorldMap
    rooms: dict[str, RoomState]
    objects: dict[str, ObjectState]
    agents: dict[str, AgentState]
    tick: int = 0

    def room_for_position(self, x: int, y: int) -> str | None:
        for room in self.rooms.values():
            if room.bounds.contains(x, y):
                return room.room_id
        return None


def build_tiny_world() -> WorldState:
    from latticeville.sim.world_loader import load_world_state

    return load_world_state()
