"""Prompt-driven LLM policy using deterministic fixtures."""

from __future__ import annotations

from latticeville.llm.fake_llm import FakeLLM
from latticeville.llm.prompts import (
    ActInput,
    PromptId,
    parse_prompt_output,
    render_prompt,
)
from latticeville.sim.contracts import Action, ActionKind, coerce_action
from latticeville.sim.world_state import AgentState


class PromptLLM(FakeLLM):
    def decide_action(
        self,
        *,
        world,
        agent: AgentState,
        valid_targets,
        plan_step: str | None = None,
    ) -> Action:
        prompt = render_prompt(
            PromptId.ACT,
            ActInput(
                agent_name=agent.name,
                valid_locations=sorted(valid_targets.locations),
                valid_objects=sorted(valid_targets.objects),
                valid_agents=sorted(valid_targets.agents),
                plan_step=plan_step,
            ),
        )
        response = self.complete_prompt(prompt_id=PromptId.ACT.value, prompt=prompt)
        parsed = parse_prompt_output(PromptId.ACT, response)
        if parsed is None:
            return Action(kind=ActionKind.IDLE)
        return coerce_action(parsed, valid_targets)


__all__ = ["PromptLLM"]
