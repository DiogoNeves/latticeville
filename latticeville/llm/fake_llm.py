"""Deterministic FakeLLM policy for tests and demos."""

from __future__ import annotations

from latticeville.llm.base import LLMPolicy
from latticeville.llm.prompt_fixtures import fixture_for
from latticeville.llm.prompts import PromptId, extract_json
from latticeville.sim.contracts import Action, ActionKind, MoveArgs, coerce_action
from latticeville.sim.world_state import AgentState


class FakeLLM(LLMPolicy):
    def decide_action(self, *, world, agent: AgentState, valid_targets) -> Action:
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
        action = Action(kind=ActionKind.MOVE, move=MoveArgs(to_location_id=destination))
        return coerce_action(action.model_dump(), valid_targets)

    def complete_prompt(self, *, prompt_id: str, prompt: str) -> str:
        payload = extract_json(prompt) or {}
        try:
            prompt_enum = PromptId(prompt_id)
        except ValueError:
            return "{}"
        return fixture_for(prompt_enum, payload)
