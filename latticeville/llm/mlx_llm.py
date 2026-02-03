"""mlx-lm adapter for real local runs."""

from __future__ import annotations

from dataclasses import dataclass

from latticeville.llm.base import LLMConfig, LLMPolicy
from latticeville.llm.prompts import (
    ActInput,
    PromptId,
    parse_prompt_output,
    render_prompt,
)
from latticeville.sim.contracts import Action, ActionKind, coerce_action
from latticeville.sim.world_state import AgentState


@dataclass
class MlxLLM(LLMPolicy):
    config: LLMConfig

    def __post_init__(self) -> None:
        from mlx_lm import load

        self._model, self._tokenizer = load(self.config.model_id)

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
                personality=agent.personality or None,
            ),
        )
        response = self.complete_prompt(prompt_id=PromptId.ACT.value, prompt=prompt)
        parsed = parse_prompt_output(PromptId.ACT, response)
        if parsed is None:
            return Action(kind=ActionKind.IDLE)
        return coerce_action(parsed, valid_targets)

    def complete_prompt(self, *, prompt_id: str, prompt: str) -> str:
        _ = prompt_id
        return _generate(self._model, self._tokenizer, prompt)


def _generate(model, tokenizer, prompt: str) -> str:
    from mlx_lm import generate

    return generate(model, tokenizer, prompt=prompt, max_tokens=256)


__all__ = ["MlxLLM"]
