"""Load world data from JSON + ASCII map."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from latticeville.sim.contracts import NodeType, WorldNode, WorldTree
from latticeville.sim.world_state import (
    AgentState,
    Bounds,
    ObjectState,
    RoomState,
    WorldMap,
    WorldState,
)
from latticeville.sim.world_tiles import is_walkable


@dataclass(frozen=True)
class WorldPaths:
    base_dir: Path = Path("world")

    @property
    def world_json(self) -> Path:
        return self.base_dir / "world.json"

    @property
    def characters_json(self) -> Path:
        return self.base_dir / "characters.json"


@dataclass(frozen=True)
class RoomDef:
    id: str
    name: str
    bounds: Bounds


@dataclass(frozen=True)
class ObjectDef:
    id: str
    name: str
    room_id: str | None
    symbol: str
    position: tuple[int, int]


@dataclass(frozen=True)
class CharacterDef:
    id: str
    name: str
    symbol: str
    start_room_id: str
    patrol_route: list[str]


@dataclass(frozen=True)
class WorldConfig:
    map_file: str
    rooms: list[RoomDef]
    objects: list[ObjectDef]
    characters: list[CharacterDef]


def load_world_config(*, paths: WorldPaths | None = None) -> WorldConfig:
    paths = paths or WorldPaths()
    world_data = _load_json(paths.world_json)
    characters_data = _load_json(paths.characters_json)

    map_file = world_data.get("map_file", "world.map")

    rooms = [
        RoomDef(
            id=room["id"],
            name=room.get("name", room["id"].title()),
            bounds=_parse_bounds(room["bounds"]),
        )
        for room in world_data.get("rooms", [])
    ]

    objects = [
        ObjectDef(
            id=obj["id"],
            name=obj.get("name", obj["id"].title()),
            room_id=obj.get("room_id"),
            symbol=obj.get("symbol", "*"),
            position=_parse_position(obj.get("position")),
        )
        for obj in world_data.get("objects", [])
    ]

    characters = [
        CharacterDef(
            id=char["id"],
            name=char.get("name", char["id"].title()),
            symbol=char.get("symbol", "@"),
            start_room_id=char["start_room_id"],
            patrol_route=char.get("patrol_route", [char["start_room_id"]]),
        )
        for char in characters_data.get("characters", [])
    ]

    return WorldConfig(
        map_file=map_file,
        rooms=rooms,
        objects=objects,
        characters=characters,
    )


def load_world_state(*, paths: WorldPaths | None = None) -> WorldState:
    config = load_world_config(paths=paths)
    map_path = (paths or WorldPaths()).base_dir / config.map_file
    world_map = _load_world_map(map_path)

    rooms = {room.id: RoomState(room_id=room.id, name=room.name, bounds=room.bounds) for room in config.rooms}
    objects = _resolve_objects(config.objects, rooms)
    blocked = {obj.position for obj in objects.values()}

    nodes: dict[str, WorldNode] = {
        "world": WorldNode(
            id="world",
            name="World",
            type=NodeType.AREA,
            parent_id=None,
            children=[room.room_id for room in rooms.values()],
        )
    }

    for room in rooms.values():
        nodes[room.room_id] = WorldNode(
            id=room.room_id,
            name=room.name,
            type=NodeType.AREA,
            parent_id="world",
            children=[],
        )

    for obj in objects.values():
        nodes[obj.object_id] = WorldNode(
            id=obj.object_id,
            name=obj.name,
            type=NodeType.OBJECT,
            parent_id=obj.room_id,
            children=[],
        )
        nodes[obj.room_id].children.append(obj.object_id)

    agents: dict[str, AgentState] = {}
    for char in config.characters:
        if char.start_room_id not in rooms:
            raise ValueError(
                f"Character start_room_id {char.start_room_id} is not defined."
            )
        start_room = rooms[char.start_room_id]
        start_pos = _find_spawn_position(world_map, start_room.bounds, blocked)
        agent_id = char.id
        nodes[agent_id] = WorldNode(
            id=agent_id,
            name=char.name,
            type=NodeType.AGENT,
            parent_id=char.start_room_id,
            children=[],
        )
        nodes[char.start_room_id].children.append(agent_id)
        agents[agent_id] = AgentState(
            agent_id=agent_id,
            name=char.name,
            location_id=char.start_room_id,
            position=start_pos,
            patrol_route=char.patrol_route,
        )

    world = WorldTree(root_id="world", nodes=nodes)
    return WorldState(
        world=world,
        world_map=world_map,
        rooms=rooms,
        objects=objects,
        agents=agents,
    )


def _load_json(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Missing world data file: {path}") from exc
    return json.loads(text)


def _load_world_map(path: Path) -> WorldMap:
    lines = path.read_text(encoding="utf-8").splitlines()
    width = max((len(line) for line in lines), default=0)
    padded = [line.ljust(width) for line in lines]
    return WorldMap(lines=padded, width=width, height=len(padded))


def _parse_bounds(data: dict[str, int]) -> Bounds:
    return Bounds(
        x=int(data["x"]),
        y=int(data["y"]),
        width=int(data["width"]),
        height=int(data["height"]),
    )


def _parse_position(data: dict[str, int] | None) -> tuple[int, int]:
    if not data:
        return (1, 1)
    return (int(data.get("x", 1)), int(data.get("y", 1)))


def _resolve_objects(
    objects: list[ObjectDef], rooms: dict[str, RoomState]
) -> dict[str, ObjectState]:
    resolved: dict[str, ObjectState] = {}
    for obj in objects:
        room_id = obj.room_id or _room_for_position(rooms, obj.position)
        if room_id is None:
            raise ValueError(f"Object {obj.id} is not inside any room.")
        resolved[obj.id] = ObjectState(
            object_id=obj.id,
            name=obj.name,
            room_id=room_id,
            symbol=obj.symbol,
            position=obj.position,
        )
    return resolved


def _room_for_position(
    rooms: dict[str, RoomState], position: tuple[int, int]
) -> str | None:
    x, y = position
    for room in rooms.values():
        if room.bounds.contains(x, y):
            return room.room_id
    return None


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
