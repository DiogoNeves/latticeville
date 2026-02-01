"""Grid-based movement helpers using A* pathfinding."""

from __future__ import annotations

from latticeville.sim.contracts import Event
from latticeville.sim.pathfinding import Grid, PathFinder
from latticeville.sim.world_state import AgentState, RoomState, WorldMap, WorldState


def build_grid(world_map: WorldMap) -> Grid:
    walls = set()
    for y, line in enumerate(world_map.lines):
        for x, ch in enumerate(line):
            if ch == "#":
                walls.add((x, y))
    return Grid(width=world_map.width, height=world_map.height, walls=walls)


def start_move(
    agent: AgentState,
    state: WorldState,
    destination_room_id: str,
    *,
    pathfinder: PathFinder,
) -> None:
    if agent.location_id == destination_room_id:
        return
    if destination_room_id not in state.rooms:
        return
    target = _pick_room_target(
        state.rooms[destination_room_id], state.world_map, _blocked_positions(state)
    )
    path = pathfinder.find_path(agent.position, target, _blocked_positions(state))
    if not path:
        return
    agent.path_remaining = path
    agent.travel_origin = agent.location_id
    agent.travel_destination = destination_room_id


def advance_movement(state: WorldState, agent: AgentState) -> Event | None:
    if not agent.path_remaining:
        return None

    next_pos = agent.path_remaining.pop(0)
    agent.position = next_pos

    next_room = state.room_for_position(*next_pos)
    if next_room and next_room != agent.location_id:
        _move_agent_node(state, agent.agent_id, next_room)
        agent.location_id = next_room

    if agent.path_remaining:
        return None

    origin = agent.travel_origin
    destination = agent.travel_destination
    agent.travel_origin = None
    agent.travel_destination = None
    if origin and destination:
        return Event(
            kind="MOVE",
            payload={"agent_id": agent.agent_id, "from": origin, "to": destination},
        )
    return None


def _blocked_positions(state: WorldState) -> set[tuple[int, int]]:
    return {obj.position for obj in state.objects.values()}


def _pick_room_target(
    room: RoomState, world_map: WorldMap, blocked: set[tuple[int, int]]
) -> tuple[int, int]:
    candidates: list[tuple[int, int]] = []
    for y in range(room.bounds.y + 1, room.bounds.y + room.bounds.height - 1):
        for x in range(room.bounds.x + 1, room.bounds.x + room.bounds.width - 1):
            if (x, y) in blocked:
                continue
            if _is_walkable(world_map, x, y):
                candidates.append((x, y))
    if candidates:
        center = (room.bounds.x + room.bounds.width // 2, room.bounds.y + room.bounds.height // 2)
        return min(candidates, key=lambda pos: abs(pos[0] - center[0]) + abs(pos[1] - center[1]))
    return (room.bounds.x + 1, room.bounds.y + 1)


def _is_walkable(world_map: WorldMap, x: int, y: int) -> bool:
    if x < 0 or y < 0 or y >= world_map.height or x >= world_map.width:
        return False
    return world_map.lines[y][x] != "#"


def _move_agent_node(state: WorldState, agent_id: str, new_room_id: str) -> None:
    agent_node = state.world.nodes[agent_id]
    old_parent_id = agent_node.parent_id

    if old_parent_id and agent_id in state.world.nodes[old_parent_id].children:
        state.world.nodes[old_parent_id].children.remove(agent_id)
    if agent_id not in state.world.nodes[new_room_id].children:
        state.world.nodes[new_room_id].children.append(agent_id)

    agent_node.parent_id = new_room_id
