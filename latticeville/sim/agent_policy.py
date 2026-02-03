"""Deterministic placeholder policy for non-LLM runs."""

from __future__ import annotations

from latticeville.sim.contracts import Action, ActionKind
from latticeville.sim.world_state import AgentState


def choose_patrol_action(agent: AgentState) -> Action:
    _ = agent
    return Action(kind=ActionKind.IDLE)
