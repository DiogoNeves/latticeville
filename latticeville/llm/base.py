"""LLM policy interface and helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from latticeville.sim.contracts import Action, ValidTargets, WorldTree
from latticeville.sim.movement import build_area_graph
from latticeville.sim.world_state import AgentState


class LLMPolicy(Protocol):
    def decide_action(
        self, *, world: WorldTree, agent: AgentState, valid_targets: ValidTargets
    ) -> Action:
        """Return one structured action for the agent."""

    def complete_prompt(self, *, prompt_id: str, prompt: str) -> str:
        """Return raw prompt completion text."""


@dataclass(frozen=True)
class LLMConfig:
    model_id: str


def build_valid_targets(
    world: WorldTree,
    *,
    agent: AgentState,
    portals: dict[str, dict[str, str]] | None = None,
) -> ValidTargets:
    graph = build_area_graph(world, portals=portals)
    locations = set(graph.keys())
    objects = {
        node.id
        for node in world.nodes.values()
        if node.type == "object" and node.parent_id == agent.location_id
    }
    agents = {
        node.id
        for node in world.nodes.values()
        if node.type == "agent"
        and node.parent_id == agent.location_id
        and node.id != agent.agent_id
    }
    return ValidTargets(locations=locations, objects=objects, agents=agents)
