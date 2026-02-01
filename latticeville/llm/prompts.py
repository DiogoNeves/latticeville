"""Prompt templates and parsing helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class PromptId(str, Enum):
    OBSERVATION = "observation"
    IMPORTANCE = "importance"
    REFLECTION_QUESTIONS = "reflection_questions"
    REFLECTION_INSIGHTS = "reflection_insights"
    DAY_PLAN = "day_plan"
    PLAN_DECOMPOSE = "plan_decompose"
    REACT = "react"
    DIALOGUE_INITIATOR = "dialogue_initiator"
    DIALOGUE_RESPONDER = "dialogue_responder"
    ACT = "act"


class ObservationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str
    location_name: str
    visible_agents: list[str] = Field(default_factory=list)
    visible_objects: list[str] = Field(default_factory=list)


class ObservationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observations: list[str]


class ImportanceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_text: str
    memory_type: str | None = None


class ImportanceOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    importance: int


class ReflectionQuestionsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statements: list[str]


class ReflectionQuestionsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[str]


class ReflectionInsightSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    supports: list[int]


class ReflectionInsightsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statements: list[str]
    questions: list[str]


class ReflectionInsightsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    insights: list[ReflectionInsightSpec]


class PlanItemSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    location: str
    duration: int = Field(ge=1)


class DayPlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str
    start_tick: int
    context: str | None = None


class DayPlanOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PlanItemSpec]


class PlanDecomposeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PlanItemSpec]
    chunk_size: int = Field(ge=1)


class PlanDecomposeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PlanItemSpec]


class ReactInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str
    observation: str
    current_plan: str | None = None


class ReactOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    react: bool
    reaction: str


class DialogueInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str
    observation: str
    context: str | None = None
    history: list[str] = Field(default_factory=list)


class DialogueOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    utterance: str


class ActInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str
    valid_locations: list[str]
    valid_objects: list[str]
    valid_agents: list[str]
    plan_step: str | None = None


@dataclass(frozen=True)
class PromptSpec:
    prompt_id: PromptId
    instruction: str
    input_model: type[BaseModel]
    output_model: type[BaseModel] | None

    def render(self, payload: BaseModel | dict[str, Any]) -> str:
        if isinstance(payload, BaseModel):
            validated = payload
        else:
            validated = self.input_model.model_validate(payload)
        body = json.dumps(validated.model_dump(), indent=2, ensure_ascii=True)
        return f"{self.instruction}\nInput JSON:\n{body}\nOutput JSON:"

    def parse(self, text: str) -> BaseModel | dict[str, Any] | None:
        data = extract_json(text)
        if data is None:
            return None
        if self.output_model is None:
            return data
        try:
            return self.output_model.model_validate(data)
        except ValidationError:
            return None


CATALOG: dict[PromptId, PromptSpec] = {
    PromptId.OBSERVATION: PromptSpec(
        prompt_id=PromptId.OBSERVATION,
        instruction=(
            "You are writing short observation memories. "
            "Return JSON with a list of brief, declarative observations."
        ),
        input_model=ObservationInput,
        output_model=ObservationOutput,
    ),
    PromptId.IMPORTANCE: PromptSpec(
        prompt_id=PromptId.IMPORTANCE,
        instruction=(
            "Rate the importance of the memory on a 1-10 scale. "
            "Return JSON with an integer importance."
        ),
        input_model=ImportanceInput,
        output_model=ImportanceOutput,
    ),
    PromptId.REFLECTION_QUESTIONS: PromptSpec(
        prompt_id=PromptId.REFLECTION_QUESTIONS,
        instruction=(
            "Generate three high-level reflection questions. "
            "Return JSON with a questions list."
        ),
        input_model=ReflectionQuestionsInput,
        output_model=ReflectionQuestionsOutput,
    ),
    PromptId.REFLECTION_INSIGHTS: PromptSpec(
        prompt_id=PromptId.REFLECTION_INSIGHTS,
        instruction=(
            "Generate 3-5 insights. Each insight should reference supporting "
            "statement indices (1-based). Return JSON with an insights list."
        ),
        input_model=ReflectionInsightsInput,
        output_model=ReflectionInsightsOutput,
    ),
    PromptId.DAY_PLAN: PromptSpec(
        prompt_id=PromptId.DAY_PLAN,
        instruction=(
            "Create a 5-8 item day plan. Each item must include a location and "
            "duration (ticks). Return JSON with an items list."
        ),
        input_model=DayPlanInput,
        output_model=DayPlanOutput,
    ),
    PromptId.PLAN_DECOMPOSE: PromptSpec(
        prompt_id=PromptId.PLAN_DECOMPOSE,
        instruction=(
            "Decompose the plan into smaller chunks with the provided chunk size. "
            "Return JSON with an items list."
        ),
        input_model=PlanDecomposeInput,
        output_model=PlanDecomposeOutput,
    ),
    PromptId.REACT: PromptSpec(
        prompt_id=PromptId.REACT,
        instruction=(
            "Decide whether to react to the observation. "
            "Return JSON with react boolean and reaction string."
        ),
        input_model=ReactInput,
        output_model=ReactOutput,
    ),
    PromptId.DIALOGUE_INITIATOR: PromptSpec(
        prompt_id=PromptId.DIALOGUE_INITIATOR,
        instruction=(
            "Write a single initiating utterance. Return JSON with an utterance field."
        ),
        input_model=DialogueInput,
        output_model=DialogueOutput,
    ),
    PromptId.DIALOGUE_RESPONDER: PromptSpec(
        prompt_id=PromptId.DIALOGUE_RESPONDER,
        instruction=(
            "Write a single response utterance. Return JSON with an utterance field."
        ),
        input_model=DialogueInput,
        output_model=DialogueOutput,
    ),
    PromptId.ACT: PromptSpec(
        prompt_id=PromptId.ACT,
        instruction=(
            "Choose exactly one action. Return only JSON matching the action schema: "
            '{ "kind": "IDLE|MOVE|INTERACT|SAY", '
            '"move": {"to_location_id": "..."}, '
            '"interact": {"object_id": "...", "verb": "USE|OPEN|CLOSE|TAKE|DROP"}, '
            '"say": {"to_agent_id": "...", "utterance": "..."} }'
        ),
        input_model=ActInput,
        output_model=None,
    ),
}


def render_prompt(prompt_id: PromptId, payload: BaseModel | dict[str, Any]) -> str:
    return CATALOG[prompt_id].render(payload)


def parse_prompt_output(
    prompt_id: PromptId, text: str
) -> BaseModel | dict[str, Any] | None:
    return CATALOG[prompt_id].parse(text)


def clamp_importance(value: int) -> int:
    return max(1, min(10, value))


def extract_json(text: str) -> dict[str, Any] | None:
    marker_start = "Input JSON:"
    marker_end = "Output JSON:"
    if marker_start in text and marker_end in text:
        block = text.split(marker_start, 1)[1].split(marker_end, 1)[0].strip()
        if block:
            try:
                loaded = json.loads(block)
            except json.JSONDecodeError:
                loaded = None
            if isinstance(loaded, dict):
                return loaded
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    snippet = text[start : end + 1]
    try:
        loaded = json.loads(snippet)
    except json.JSONDecodeError:
        return None
    if isinstance(loaded, dict):
        return loaded
    return None


def summarize_statements(statements: Iterable[str], *, limit: int = 5) -> str:
    trimmed = list(statements)[:limit]
    return "; ".join(trimmed)
