"""Deterministic prompt fixtures for FakeLLM and tests."""

from __future__ import annotations

import json
from typing import Any

from latticeville.llm.prompts import (
    ActInput,
    DayPlanInput,
    DialogueInput,
    ImportanceInput,
    ObservationInput,
    PlanDecomposeInput,
    PromptId,
    ReactInput,
    ReflectionInsightsInput,
    ReflectionQuestionsInput,
)


def fixture_for(prompt_id: PromptId, payload: Any) -> str:
    if prompt_id == PromptId.OBSERVATION:
        data = ObservationInput.model_validate(payload)
        observations = [f"{data.agent_name} is at {data.location_name}."]
        if data.visible_agents:
            observations.append(
                f"{data.agent_name} sees {', '.join(data.visible_agents)} nearby."
            )
        if data.visible_objects:
            observations.append(
                f"{data.agent_name} notices {', '.join(data.visible_objects)}."
            )
        return _dump({"observations": observations})

    if prompt_id == PromptId.IMPORTANCE:
        data = ImportanceInput.model_validate(payload)
        base = _importance_by_type(data.memory_type)
        return _dump({"importance": base})

    if prompt_id == PromptId.REFLECTION_QUESTIONS:
        _ = ReflectionQuestionsInput.model_validate(payload)
        return _dump(
            {
                "questions": [
                    "What patterns are emerging?",
                    "What is the main focus right now?",
                    "What should be followed up on?",
                ]
            }
        )

    if prompt_id == PromptId.REFLECTION_INSIGHTS:
        data = ReflectionInsightsInput.model_validate(payload)
        count = max(1, min(3, len(data.statements)))
        insights = []
        for index in range(count):
            supports = _supports_for(index, len(data.statements))
            insights.append(
                {
                    "text": f"Insight {index + 1} based on recent memories.",
                    "supports": supports,
                }
            )
        return _dump({"insights": insights})

    if prompt_id == PromptId.DAY_PLAN:
        data = DayPlanInput.model_validate(payload)
        items = _default_day_plan(data.agent_name)
        return _dump({"items": items})

    if prompt_id == PromptId.PLAN_DECOMPOSE:
        data = PlanDecomposeInput.model_validate(payload)
        items = _decompose_items(data.items, chunk_size=data.chunk_size)
        return _dump({"items": items})

    if prompt_id == PromptId.REACT:
        _ = ReactInput.model_validate(payload)
        return _dump({"react": False, "reaction": "Keeps to the plan."})

    if prompt_id in {PromptId.DIALOGUE_INITIATOR, PromptId.DIALOGUE_RESPONDER}:
        data = DialogueInput.model_validate(payload)
        return _dump({"utterance": f"{data.agent_name} says hello."})

    if prompt_id == PromptId.ACT:
        data = ActInput.model_validate(payload)
        target = data.valid_locations[0] if data.valid_locations else ""
        return _dump({"kind": "MOVE", "move": {"to_location_id": target}})

    return _dump({})


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True)


def _importance_by_type(memory_type: str | None) -> int:
    mapping = {
        "observation": 2,
        "action": 3,
        "plan": 1,
        "reflection": 3,
    }
    return mapping.get(memory_type or "", 2)


def _supports_for(index: int, total: int) -> list[int]:
    if total <= 1:
        return [1]
    start = index + 1
    end = min(total, start + 1)
    return [start, end]


def _default_day_plan(agent_name: str) -> list[dict[str, Any]]:
    return [
        {
            "location": "street",
            "description": f"{agent_name} starts the day and checks the surroundings.",
            "duration": 4,
        },
        {
            "location": "cafe",
            "description": f"{agent_name} spends time at the cafe and observes activity.",
            "duration": 4,
        },
        {
            "location": "park",
            "description": f"{agent_name} takes a short walk and reflects.",
            "duration": 4,
        },
        {
            "location": "street",
            "description": f"{agent_name} does a short errand and returns.",
            "duration": 4,
        },
        {
            "location": "cafe",
            "description": f"{agent_name} wraps up with a final stop at the cafe.",
            "duration": 4,
        },
    ]


def _decompose_items(items: list[Any], *, chunk_size: int) -> list[dict[str, Any]]:
    decomposed: list[dict[str, Any]] = []
    for item in items:
        payload = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        duration = int(payload.get("duration", 1))
        remaining = max(1, duration)
        while remaining > 0:
            step = min(chunk_size, remaining)
            decomposed.append(
                {
                    "location": payload.get("location", "street"),
                    "description": f"{payload.get('description', '').strip()} (action slice)",
                    "duration": step,
                }
            )
            remaining -= step
    return decomposed
