"""World and agent runtime state for the minimal sim loop."""

from __future__ import annotations

from dataclasses import dataclass, field

from latticeville.sim.contracts import NodeType, WorldNode, WorldTree


@dataclass
class AgentState:
    agent_id: str
    name: str
    location_id: str
    patrol_route: list[str]
    route_index: int = 0
    direction: int = 1
    path_remaining: list[str] = field(default_factory=list)
    travel_origin: str | None = None
    travel_destination: str | None = None

    def set_route_index(self, location_id: str) -> None:
        if location_id in self.patrol_route:
            self.route_index = self.patrol_route.index(location_id)


@dataclass
class WorldState:
    world: WorldTree
    agents: dict[str, AgentState]
    tick: int = 0


def build_tiny_world() -> WorldState:
    nodes = {
        "world": WorldNode(
            id="world",
            name="World",
            type=NodeType.AREA,
            parent_id=None,
            children=["street"],
        ),
        "street": WorldNode(
            id="street",
            name="Neon Street",
            type=NodeType.AREA,
            parent_id="world",
            children=["cafe", "ada", "byron"],
        ),
        "cafe": WorldNode(
            id="cafe",
            name="Cafe",
            type=NodeType.AREA,
            parent_id="street",
            children=["park"],
        ),
        "park": WorldNode(
            id="park",
            name="Park",
            type=NodeType.AREA,
            parent_id="cafe",
            children=[],
        ),
        "ada": WorldNode(
            id="ada",
            name="Ada",
            type=NodeType.AGENT,
            parent_id="street",
            children=[],
        ),
        "byron": WorldNode(
            id="byron",
            name="Byron",
            type=NodeType.AGENT,
            parent_id="street",
            children=[],
        ),
    }
    world = WorldTree(root_id="world", nodes=nodes)
    agents = {
        "ada": AgentState(
            agent_id="ada",
            name="Ada",
            location_id="street",
            patrol_route=["street", "park"],
        ),
        "byron": AgentState(
            agent_id="byron",
            name="Byron",
            location_id="street",
            patrol_route=["street", "cafe"],
        ),
    }
    return WorldState(world=world, agents=agents)
