"""Load world data from JSON + ASCII maps."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from latticeville.sim.contracts import NodeType, WorldNode, WorldTree
from latticeville.sim.world_state import AgentState, WorldState


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
class AreaDef:
    id: str
    name: str
    map_file: str
    portals: dict[str, str]


@dataclass(frozen=True)
class ObjectDef:
    id: str
    name: str
    area_id: str
    symbol: str
    position: dict[str, int] | None
    tile: str | None


@dataclass(frozen=True)
class CharacterDef:
    id: str
    name: str
    symbol: str
    start_area_id: str
    patrol_route: list[str]


@dataclass(frozen=True)
class WorldConfig:
    areas: list[AreaDef]
    objects: list[ObjectDef]
    characters: list[CharacterDef]


def load_world_config(*, paths: WorldPaths | None = None) -> WorldConfig:
    paths = paths or WorldPaths()
    world_data = _load_json(paths.world_json)
    characters_data = _load_json(paths.characters_json)

    areas = [
        AreaDef(
            id=area["id"],
            name=area["name"],
            map_file=area["map_file"],
            portals=area.get("portals", {}),
        )
        for area in world_data.get("areas", [])
    ]
    objects = [
        ObjectDef(
            id=obj["id"],
            name=obj["name"],
            area_id=obj["area_id"],
            symbol=obj.get("symbol", "*"),
            position=obj.get("position"),
            tile=obj.get("tile"),
        )
        for obj in world_data.get("objects", [])
    ]
    characters = [
        CharacterDef(
            id=char["id"],
            name=char["name"],
            symbol=char.get("symbol", "@"),
            start_area_id=char["start_area_id"],
            patrol_route=char.get("patrol_route", [char["start_area_id"]]),
        )
        for char in characters_data.get("characters", [])
    ]
    return WorldConfig(areas=areas, objects=objects, characters=characters)


def load_world_state(*, paths: WorldPaths | None = None) -> WorldState:
    config = load_world_config(paths=paths)
    area_ids = {area.id for area in config.areas}
    _validate_portals(config.areas, area_ids)

    nodes: dict[str, WorldNode] = {
        "world": WorldNode(
            id="world",
            name="World",
            type=NodeType.AREA,
            parent_id=None,
            children=[area.id for area in config.areas],
        )
    }

    for area in config.areas:
        nodes[area.id] = WorldNode(
            id=area.id,
            name=area.name,
            type=NodeType.AREA,
            parent_id="world",
            children=[],
        )

    for obj in config.objects:
        area_id = obj.area_id
        if area_id not in area_ids:
            raise ValueError(f"Object area_id {area_id} is not defined.")
        obj_id = obj.id
        nodes[obj_id] = WorldNode(
            id=obj_id,
            name=obj.name,
            type=NodeType.OBJECT,
            parent_id=area_id,
            children=[],
        )
        nodes[area_id].children.append(obj_id)

    agents: dict[str, AgentState] = {}
    for char in config.characters:
        start_area = char.start_area_id
        if start_area not in area_ids:
            raise ValueError(f"Character start_area_id {start_area} is not defined.")
        agent_id = char.id
        nodes[agent_id] = WorldNode(
            id=agent_id,
            name=char.name,
            type=NodeType.AGENT,
            parent_id=start_area,
            children=[],
        )
        nodes[start_area].children.append(agent_id)
        agents[agent_id] = AgentState(
            agent_id=agent_id,
            name=char.name,
            location_id=start_area,
            patrol_route=char.patrol_route,
        )

    world = WorldTree(root_id="world", nodes=nodes)
    portals = {area.id: dict(area.portals) for area in config.areas}
    return WorldState(world=world, agents=agents, portals=portals)


def _load_json(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Missing world data file: {path}") from exc
    return json.loads(text)


def _validate_portals(areas: list[AreaDef], area_ids: set[str]) -> None:
    for area in areas:
        portals = area.portals
        for digit, destination in portals.items():
            if destination not in area_ids:
                raise ValueError(
                    f"Area {area.id} portal {digit} points to unknown {destination}."
                )
