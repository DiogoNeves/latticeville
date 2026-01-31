"""mlx-lm adapter for real local runs."""

from __future__ import annotations

import json
from dataclasses import dataclass

from latticeville.llm.base import LLMConfig, LLMPolicy
from latticeville.sim.contracts import Action, ActionKind, coerce_action
from latticeville.sim.world_state import AgentState


@dataclass
class MlxLLM(LLMPolicy):
    config: LLMConfig

    def __post_init__(self) -> None:
        from mlx_lm import load

        self._model, self._tokenizer = load(self.config.model_id)

    def decide_action(self, *, world, agent: AgentState, valid_targets) -> Action:
        prompt = _build_prompt(agent, valid_targets)
        response = _generate(self._model, self._tokenizer, prompt)
        parsed = _extract_json(response)
        if parsed is None:
            return Action(kind=ActionKind.IDLE)
        return coerce_action(parsed, valid_targets)


def _generate(model, tokenizer, prompt: str) -> str:
    from mlx_lm import generate

    return generate(model, tokenizer, prompt=prompt, max_tokens=256)


def _build_prompt(agent: AgentState, valid_targets) -> str:
    locations = sorted(valid_targets.locations)
    objects = sorted(valid_targets.objects)
    agents = sorted(valid_targets.agents)
    return (
        "Return exactly one JSON object for the action.\n"
        "Schema:\n"
        '{ "kind": "IDLE|MOVE|INTERACT|SAY",'
        ' "move": {"to_location_id": "..."},'
        ' "interact": {"object_id": "...", "verb": "USE|OPEN|CLOSE|TAKE|DROP"},'
        ' "say": {"to_agent_id": "...", "utterance": "..."} }\n'
        "Only include the JSON object in the response.\n"
        f"Agent: {agent.name}\n"
        f"Valid locations: {locations}\n"
        f"Valid objects: {objects}\n"
        f"Valid agents: {agents}\n"
    )


def _extract_json(text: str) -> dict | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    snippet = text[start : end + 1]
    try:
        return json.loads(snippet)
    except json.JSONDecodeError:
        return None
