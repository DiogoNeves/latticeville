"""World and agent runtime state for the minimal sim loop."""

from __future__ import annotations

from dataclasses import dataclass, field

from latticeville.sim.contracts import WorldTree


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
    portals: dict[str, dict[str, str]] = field(default_factory=dict)
    tick: int = 0


def build_tiny_world() -> WorldState:
    from latticeville.sim.world_loader import load_world_state

    return load_world_state()
