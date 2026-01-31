"""Deterministic movement helpers for the minimal sim loop."""

from __future__ import annotations

from collections import deque

from latticeville.sim.contracts import Event, NodeType, WorldTree
from latticeville.sim.world_state import AgentState


def build_area_graph(
    world: WorldTree, *, portals: dict[str, dict[str, str]] | None = None
) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for node in world.nodes.values():
        if node.type != NodeType.AREA:
            continue
        graph.setdefault(node.id, set())
        if node.parent_id and world.nodes[node.parent_id].type == NodeType.AREA:
            graph[node.id].add(node.parent_id)
            graph.setdefault(node.parent_id, set()).add(node.id)
        for child_id in node.children:
            child = world.nodes.get(child_id)
            if child and child.type == NodeType.AREA:
                graph[node.id].add(child_id)
                graph.setdefault(child_id, set()).add(node.id)
    if portals:
        for area_id, links in portals.items():
            graph.setdefault(area_id, set())
            for destination in links.values():
                graph.setdefault(destination, set())
                graph[area_id].add(destination)
    return graph


def find_path(
    world: WorldTree,
    start: str,
    goal: str,
    *,
    portals: dict[str, dict[str, str]] | None = None,
) -> list[str]:
    if start == goal:
        return []
    graph = build_area_graph(world, portals=portals)
    if start not in graph or goal not in graph:
        return []

    queue: deque[str] = deque([start])
    came_from: dict[str, str | None] = {start: None}

    while queue:
        current = queue.popleft()
        if current == goal:
            break
        for neighbor in sorted(graph[current]):
            if neighbor in came_from:
                continue
            came_from[neighbor] = current
            queue.append(neighbor)

    if goal not in came_from:
        return []

    path: list[str] = []
    current: str | None = goal
    while current is not None and current != start:
        path.append(current)
        current = came_from[current]
    path.reverse()
    return path


def start_move(
    agent: AgentState,
    world: WorldTree,
    destination: str,
    *,
    portals: dict[str, dict[str, str]] | None = None,
) -> None:
    if agent.location_id == destination:
        return
    path = find_path(world, agent.location_id, destination, portals=portals)
    if not path:
        return
    agent.path_remaining = path
    agent.travel_origin = agent.location_id
    agent.travel_destination = destination


def advance_movement(world: WorldTree, agent: AgentState) -> Event | None:
    if not agent.path_remaining:
        return None

    next_location = agent.path_remaining.pop(0)
    move_agent_node(world, agent.agent_id, next_location)
    agent.location_id = next_location

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


def move_agent_node(world: WorldTree, agent_id: str, new_parent_id: str) -> None:
    agent_node = world.nodes[agent_id]
    old_parent_id = agent_node.parent_id

    if old_parent_id and agent_id in world.nodes[old_parent_id].children:
        world.nodes[old_parent_id].children.remove(agent_id)
    if agent_id not in world.nodes[new_parent_id].children:
        world.nodes[new_parent_id].children.append(agent_id)

    agent_node.parent_id = new_parent_id
