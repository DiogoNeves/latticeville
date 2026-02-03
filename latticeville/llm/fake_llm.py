"""Deterministic FakeLLM policy for tests and demos."""

from __future__ import annotations

from latticeville.llm.base import LLMPolicy
from latticeville.llm.prompt_fixtures import fixture_for
from latticeville.llm.prompts import (
    ActInput,
    PromptId,
    extract_json,
    parse_prompt_output,
    render_prompt,
)
from latticeville.sim.contracts import Action, ActionKind, coerce_action
from latticeville.sim.world_state import AgentState


class FakeLLM(LLMPolicy):
    def decide_action(
        self,
        *,
        world,
        agent: AgentState,
        valid_targets,
        plan_step: str | None = None,
    ) -> Action:
        _ = world
        prompt = render_prompt(
            PromptId.ACT,
            ActInput(
                agent_name=agent.name,
                valid_locations=sorted(valid_targets.locations),
                valid_objects=sorted(valid_targets.objects),
                valid_agents=sorted(valid_targets.agents),
                plan_step=plan_step,
                personality=agent.personality or None,
            ),
        )
        response = self.complete_prompt(prompt_id=PromptId.ACT.value, prompt=prompt)
        parsed = parse_prompt_output(PromptId.ACT, response)
        if parsed is None:
            return Action(kind=ActionKind.IDLE)
        return coerce_action(parsed, valid_targets)

    def complete_prompt(self, *, prompt_id: str, prompt: str) -> str:
        payload = extract_json(prompt) or {}
        try:
            prompt_enum = PromptId(prompt_id)
        except ValueError:
            return "{}"
        return fixture_for(prompt_enum, payload)
