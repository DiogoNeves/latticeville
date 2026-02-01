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
    overview_symbol: str | None
    overview_anchor: dict[str, int] | None
    portals: dict[str, str]


@dataclass(frozen=True)
class ObjectDef:
    id: str
    name: str
    area_id: str
    symbol: str
    position: dict[str, int] | None
    tile: str | None
    subarea_id: str | None


@dataclass(frozen=True)
class SubAreaDef:
    id: str
    name: str
    area_id: str


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
    subareas: list[SubAreaDef]
    objects: list[ObjectDef]
    characters: list[CharacterDef]
    overview_map_file: str | None


def load_world_config(*, paths: WorldPaths | None = None) -> WorldConfig:
    paths = paths or WorldPaths()
    world_data = _load_json(paths.world_json)
    characters_data = _load_json(paths.characters_json)

    areas = [
        AreaDef(
            id=area["id"],
            name=area["name"],
            map_file=area["map_file"],
            overview_symbol=area.get("overview_symbol"),
            overview_anchor=area.get("overview_anchor"),
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
            subarea_id=obj.get("subarea_id"),
        )
        for obj in world_data.get("objects", [])
    ]
    raw_subareas = world_data.get("subareas", [])
    subareas = [
        SubAreaDef(
            id=sub["id"],
            name=sub["name"],
            area_id=sub["area_id"],
        )
        for sub in raw_subareas
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
    subareas = _ensure_subareas(areas, subareas)
    return WorldConfig(
        areas=areas,
        subareas=subareas,
        objects=objects,
        characters=characters,
        overview_map_file=world_data.get("overview_map_file"),
    )


def load_world_state(*, paths: WorldPaths | None = None) -> WorldState:
    config = load_world_config(paths=paths)
    area_ids = {area.id for area in config.areas}
    _validate_portals(config.areas, area_ids)
    subareas_by_area = _subareas_by_area(config.subareas)

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

    for subarea in config.subareas:
        if subarea.area_id not in area_ids:
            raise ValueError(f"Subarea area_id {subarea.area_id} is not defined.")
        nodes[subarea.id] = WorldNode(
            id=subarea.id,
            name=subarea.name,
            type=NodeType.SUBAREA,
            parent_id=subarea.area_id,
            children=[],
        )
        nodes[subarea.area_id].children.append(subarea.id)

    for obj in config.objects:
        area_id = obj.area_id
        if area_id not in area_ids:
            raise ValueError(f"Object area_id {area_id} is not defined.")
        subarea_id = _resolve_object_subarea(
            obj,
            subareas_by_area,
            default_subarea=_default_subarea_id(subareas_by_area, area_id),
        )
        obj_id = obj.id
        nodes[obj_id] = WorldNode(
            id=obj_id,
            name=obj.name,
            type=NodeType.OBJECT,
            parent_id=subarea_id,
            children=[],
        )
        nodes[subarea_id].children.append(obj_id)

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


def _ensure_subareas(
    areas: list[AreaDef], subareas: list[SubAreaDef]
) -> list[SubAreaDef]:
    by_area = _subareas_by_area(subareas)
    ensured: list[SubAreaDef] = list(subareas)
    for area in areas:
        if by_area.get(area.id):
            continue
        ensured.append(
            SubAreaDef(
                id=f"{area.id}_core",
                name=f"{area.name} Core",
                area_id=area.id,
            )
        )
    return ensured


def _subareas_by_area(subareas: list[SubAreaDef]) -> dict[str, list[SubAreaDef]]:
    grouped: dict[str, list[SubAreaDef]] = {}
    for sub in subareas:
        grouped.setdefault(sub.area_id, []).append(sub)
    return grouped


def _default_subarea_id(
    subareas_by_area: dict[str, list[SubAreaDef]], area_id: str
) -> str:
    options = subareas_by_area.get(area_id)
    if options:
        return options[0].id
    return f"{area_id}_core"


def _resolve_object_subarea(
    obj: ObjectDef,
    subareas_by_area: dict[str, list[SubAreaDef]],
    *,
    default_subarea: str,
) -> str:
    if obj.subarea_id:
        return obj.subarea_id
    return default_subarea
