"""Deterministic patrol policy for Phase 1."""

from __future__ import annotations

from latticeville.sim.contracts import Action, ActionKind, MoveArgs
from latticeville.sim.world_state import AgentState


def choose_patrol_action(agent: AgentState) -> Action:
    if len(agent.patrol_route) < 2:
        return Action(kind=ActionKind.IDLE)

    if agent.path_remaining:
        return Action(kind=ActionKind.IDLE)

    if agent.location_id in agent.patrol_route:
        agent.route_index = agent.patrol_route.index(agent.location_id)

    next_index = agent.route_index + agent.direction
    if next_index >= len(agent.patrol_route) or next_index < 0:
        agent.direction *= -1
        next_index = agent.route_index + agent.direction

    if next_index < 0 or next_index >= len(agent.patrol_route):
        return Action(kind=ActionKind.IDLE)

    destination = agent.patrol_route[next_index]
    if destination == agent.location_id:
        return Action(kind=ActionKind.IDLE)

    return Action(kind=ActionKind.MOVE, move=MoveArgs(to_location_id=destination))
