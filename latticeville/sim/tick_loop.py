"""Tick loop orchestration for the minimal simulator."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from latticeville.db.memory_log import append_memory_record
from latticeville.llm.base import LLMPolicy, build_valid_targets
from latticeville.llm.embedder import Embedder, FakeEmbedder
from latticeville.llm.fake_llm import FakeLLM
from latticeville.llm.prompts import (
    DayPlanInput,
    DialogueInput,
    ImportanceInput,
    ObservationInput,
    PlanDecomposeInput,
    PlanItemSpec,
    PromptId,
    ReactInput,
    ReflectionInsightsInput,
    ReflectionQuestionsInput,
    clamp_importance,
    parse_prompt_output,
    render_prompt,
)
from latticeville.sim.contracts import ActionKind, Event, StateSnapshot, TickPayload
from latticeville.sim.memory import MemoryStream
from latticeville.sim.movement import advance_movement, start_move
from latticeville.sim.planning import PlanItem, build_day_plan, decompose_to_actions
from latticeville.sim.reflection import ReflectionState, build_reflections
from latticeville.sim.world_state import WorldState


def run_ticks(
    state: WorldState,
    ticks: int | None,
    *,
    policy: LLMPolicy | None = None,
    embedder: Embedder | None = None,
    memory_log_path: Path | None = None,
) -> Iterable[TickPayload]:
    llm_policy = policy or FakeLLM()
    memory_embedder = embedder or FakeEmbedder()
    memory_streams = {
        agent_id: MemoryStream(embedder=memory_embedder)
        for agent_id in state.agents.keys()
    }
    reflection_states = {
        agent_id: ReflectionState(threshold=10.0) for agent_id in state.agents.keys()
    }
    plan_cache: dict[str, list[PlanItem]] = {}
    step_count = 0
    while ticks is None or step_count < ticks:
        world_snapshot = state.world.model_copy(deep=True)
        snapshot_locations = {
            agent_id: agent.location_id for agent_id, agent in state.agents.items()
        }

        actions = {}
        for agent_id in sorted(state.agents.keys()):
            agent = state.agents[agent_id]
            agent.location_id = snapshot_locations[agent_id]
            valid_targets = build_valid_targets(
                world_snapshot, agent=agent, portals=state.portals
            )
            actions[agent_id] = llm_policy.decide_action(
                world=world_snapshot,
                agent=agent,
                valid_targets=valid_targets,
            )

        for agent_id, action in actions.items():
            if action.kind != ActionKind.MOVE:
                continue
            agent = state.agents[agent_id]
            if agent.path_remaining:
                continue
            if action.move is None:
                continue
            start_move(
                agent,
                state.world,
                action.move.to_location_id,
                portals=state.portals,
            )

        events: list[Event] = []
        move_events_by_agent: dict[str, Event] = {}
        for agent_id in sorted(state.agents.keys()):
            agent = state.agents[agent_id]
            event = advance_movement(state.world, agent)
            if event:
                events.append(event)
                move_events_by_agent[agent_id] = event
                if agent.travel_destination is None:
                    agent.set_route_index(agent.location_id)

        tick_id = state.tick + 1
        memory_events: list[Event] = []
        for agent_id in sorted(state.agents.keys()):
            agent = state.agents[agent_id]
            stream = memory_streams[agent_id]
            reflection_state = reflection_states[agent_id]
            location_node = state.world.nodes.get(agent.location_id)
            location_name = location_node.name if location_node else agent.location_id
            observations = _generate_observations(
                llm_policy,
                agent_name=agent.name,
                location_name=location_name,
                visible_agents=_visible_agents(state.world, agent),
                visible_objects=_visible_objects(state.world, agent),
            )
            for observation in observations:
                importance = _score_importance(
                    llm_policy,
                    memory_text=observation,
                    memory_type="observation",
                )
                record = stream.append(
                    description=observation,
                    created_at=tick_id,
                    importance=importance,
                    type="observation",
                )
                reflection_state.record_importance(record.importance)
                if memory_log_path:
                    append_memory_record(
                        memory_log_path, agent_id=agent_id, record=record
                    )

            say_event: Event | None = None
            action = actions.get(agent_id)
            if action and action.kind == ActionKind.SAY and action.say is not None:
                utterance = _generate_dialogue(
                    llm_policy,
                    agent_name=agent.name,
                    target_agent_id=action.say.to_agent_id,
                    observation=f"{agent.name} is initiating a conversation.",
                )
                if utterance:
                    action.say.utterance = utterance
                say_desc = (
                    f"{agent.name} says to {action.say.to_agent_id}: "
                    f'"{action.say.utterance}".'
                )
                say_event = Event(
                    kind="SAY",
                    payload={
                        "agent_id": agent_id,
                        "to_agent_id": action.say.to_agent_id,
                        "utterance": action.say.utterance,
                        "area_id": agent.location_id,
                    },
                )
                say_importance = _score_importance(
                    llm_policy,
                    memory_text=say_desc,
                    memory_type="action",
                )
                say_record = stream.append(
                    description=say_desc,
                    created_at=tick_id,
                    importance=say_importance,
                    type="action",
                )
                reflection_state.record_importance(say_record.importance)
                if memory_log_path:
                    append_memory_record(
                        memory_log_path, agent_id=agent_id, record=say_record
                    )

            move_event = move_events_by_agent.get(agent_id)
            if move_event:
                move_desc = (
                    f"{agent.name} moved from {move_event.payload.get('from')} "
                    f"to {move_event.payload.get('to')}."
                )
                move_importance = _score_importance(
                    llm_policy,
                    memory_text=move_desc,
                    memory_type="action",
                )
                move_record = stream.append(
                    description=move_desc,
                    created_at=tick_id,
                    importance=move_importance,
                    type="action",
                )
                reflection_state.record_importance(move_record.importance)
                if memory_log_path:
                    append_memory_record(
                        memory_log_path,
                        agent_id=agent_id,
                        record=move_record,
                    )
            if say_event:
                events.append(say_event)

            if agent_id not in plan_cache:
                day_plan = _build_day_plan(llm_policy, agent.name, tick_id)
                decomposed = _decompose_plan(llm_policy, day_plan)
                plan_cache[agent_id] = decomposed
                for item in day_plan:
                    plan_importance = _score_importance(
                        llm_policy,
                        memory_text=item.description,
                        memory_type="plan",
                    )
                    plan_record = stream.append(
                        description=item.description,
                        created_at=tick_id,
                        importance=plan_importance,
                        type="plan",
                    )
                    if memory_log_path:
                        append_memory_record(
                            memory_log_path,
                            agent_id=agent_id,
                            record=plan_record,
                        )

            active_plan = None
            for item in plan_cache[agent_id]:
                if item.start_tick <= tick_id < item.end_tick:
                    active_plan = item
                    break
            if active_plan:
                memory_events.append(
                    Event(
                        kind="PLAN_SUMMARY",
                        payload={
                            "agent_id": agent_id,
                            "start_tick": active_plan.start_tick,
                            "end_tick": active_plan.end_tick,
                            "location": active_plan.location,
                            "description": active_plan.description,
                        },
                    )
                )

            observation_summary = observations[0] if observations else ""
            react_output = _check_reaction(
                llm_policy,
                agent_name=agent.name,
                observation=observation_summary,
                active_plan=active_plan.description if active_plan else None,
            )
            if react_output and react_output.react:
                reaction_text = (
                    f"{agent.name} decides to react: {react_output.reaction}"
                )
                reaction_importance = _score_importance(
                    llm_policy,
                    memory_text=reaction_text,
                    memory_type="reflection",
                )
                reaction_record = stream.append(
                    description=reaction_text,
                    created_at=tick_id,
                    importance=reaction_importance,
                    type="reflection",
                )
                reflection_state.record_importance(reaction_record.importance)
                if memory_log_path:
                    append_memory_record(
                        memory_log_path, agent_id=agent_id, record=reaction_record
                    )
                day_plan = _build_day_plan(
                    llm_policy,
                    agent.name,
                    tick_id,
                    context=react_output.reaction,
                )
                decomposed = _decompose_plan(llm_policy, day_plan)
                plan_cache[agent_id] = decomposed
                for item in day_plan:
                    plan_importance = _score_importance(
                        llm_policy,
                        memory_text=item.description,
                        memory_type="plan",
                    )
                    plan_record = stream.append(
                        description=item.description,
                        created_at=tick_id,
                        importance=plan_importance,
                        type="plan",
                    )
                    if memory_log_path:
                        append_memory_record(
                            memory_log_path,
                            agent_id=agent_id,
                            record=plan_record,
                        )

            query = f"{agent.name} at {location_name}."
            retrieved = stream.retrieve(query=query, current_tick=tick_id, k=3)
            memory_events.append(
                Event(
                    kind="MEMORY_SUMMARY",
                    payload={
                        "agent_id": agent_id,
                        "total": len(stream.records),
                        "latest": [rec.description for rec in stream.records[-3:]],
                        "retrieved": [
                            result.record.description for result in retrieved
                        ],
                    },
                )
            )

            if reflection_state.should_reflect():
                insights = _build_reflection_insights(
                    llm_policy,
                    agent_name=agent.name,
                    supporting=[result.record for result in retrieved],
                )
                for description, links in insights:
                    reflection_importance = _score_importance(
                        llm_policy,
                        memory_text=description,
                        memory_type="reflection",
                    )
                    reflection_record = stream.append(
                        description=description,
                        created_at=tick_id,
                        importance=reflection_importance,
                        type="reflection",
                        links=links,
                    )
                    if memory_log_path:
                        append_memory_record(
                            memory_log_path,
                            agent_id=agent_id,
                            record=reflection_record,
                        )
                reflection_state.reset()
                memory_events.append(
                    Event(
                        kind="REFLECTION_SUMMARY",
                        payload={
                            "agent_id": agent_id,
                            "count": len(insights),
                            "items": [item[0] for item in insights],
                        },
                    )
                )

        events.extend(memory_events)
        state.tick += 1
        world_snapshot = state.world.model_copy(deep=True)
        payload = TickPayload(
            tick=state.tick,
            state=StateSnapshot(world=world_snapshot, beliefs={}),
            events=events or None,
        )
        yield payload
        step_count += 1


def _run_prompt(policy: LLMPolicy, prompt_id: PromptId, payload) -> object | None:
    prompt = render_prompt(prompt_id, payload)
    response = policy.complete_prompt(prompt_id=prompt_id.value, prompt=prompt)
    return parse_prompt_output(prompt_id, response)


def _generate_observations(
    policy: LLMPolicy,
    *,
    agent_name: str,
    location_name: str,
    visible_agents: list[str],
    visible_objects: list[str],
) -> list[str]:
    output = _run_prompt(
        policy,
        PromptId.OBSERVATION,
        ObservationInput(
            agent_name=agent_name,
            location_name=location_name,
            visible_agents=visible_agents,
            visible_objects=visible_objects,
        ),
    )
    if output and getattr(output, "observations", None):
        return list(output.observations)
    return [f"{agent_name} is at {location_name}."]


def _score_importance(
    policy: LLMPolicy, *, memory_text: str, memory_type: str
) -> float:
    output = _run_prompt(
        policy,
        PromptId.IMPORTANCE,
        ImportanceInput(memory_text=memory_text, memory_type=memory_type),
    )
    if output and getattr(output, "importance", None):
        return float(clamp_importance(int(output.importance)))
    fallback = {
        "observation": 2.0,
        "action": 3.0,
        "plan": 1.0,
        "reflection": 3.0,
    }
    return fallback.get(memory_type, 2.0)


def _build_day_plan(
    policy: LLMPolicy, agent_name: str, start_tick: int, context: str | None = None
) -> list[PlanItem]:
    output = _run_prompt(
        policy,
        PromptId.DAY_PLAN,
        DayPlanInput(agent_name=agent_name, start_tick=start_tick, context=context),
    )
    if output and getattr(output, "items", None):
        specs = [PlanItemSpec.model_validate(item) for item in output.items]
        return _specs_to_plan(specs, start_tick=start_tick)
    return build_day_plan(agent_name, start_tick=start_tick)


def _decompose_plan(policy: LLMPolicy, plan: list[PlanItem]) -> list[PlanItem]:
    specs = [
        PlanItemSpec(
            description=item.description,
            location=item.location,
            duration=max(1, item.end_tick - item.start_tick),
        )
        for item in plan
    ]
    output = _run_prompt(
        policy,
        PromptId.PLAN_DECOMPOSE,
        PlanDecomposeInput(items=specs, chunk_size=1),
    )
    if output and getattr(output, "items", None):
        decomposed_specs = [PlanItemSpec.model_validate(item) for item in output.items]
        return _specs_to_plan(decomposed_specs, start_tick=plan[0].start_tick)
    return decompose_to_actions(plan)


def _check_reaction(
    policy: LLMPolicy,
    *,
    agent_name: str,
    observation: str,
    active_plan: str | None,
):
    if not observation:
        return None
    return _run_prompt(
        policy,
        PromptId.REACT,
        ReactInput(
            agent_name=agent_name,
            observation=observation,
            current_plan=active_plan,
        ),
    )


def _generate_dialogue(
    policy: LLMPolicy,
    *,
    agent_name: str,
    target_agent_id: str,
    observation: str,
) -> str | None:
    output = _run_prompt(
        policy,
        PromptId.DIALOGUE_INITIATOR,
        DialogueInput(
            agent_name=agent_name,
            observation=observation,
            context=f"Speaking to {target_agent_id}.",
            history=[],
        ),
    )
    if output and getattr(output, "utterance", None):
        return output.utterance
    return None


def _build_reflection_insights(
    policy: LLMPolicy,
    *,
    agent_name: str,
    supporting,
) -> list[tuple[str, list[str]]]:
    statements = [record.description for record in supporting]
    if not statements:
        return []
    questions_output = _run_prompt(
        policy,
        PromptId.REFLECTION_QUESTIONS,
        ReflectionQuestionsInput(statements=statements),
    )
    questions = (
        list(questions_output.questions)
        if questions_output and getattr(questions_output, "questions", None)
        else []
    )
    insights_output = _run_prompt(
        policy,
        PromptId.REFLECTION_INSIGHTS,
        ReflectionInsightsInput(statements=statements, questions=questions),
    )
    if insights_output and getattr(insights_output, "insights", None):
        insights = []
        for insight in insights_output.insights:
            links = _map_supports_to_links(insight.supports, supporting)
            insights.append((insight.text, links))
        return insights
    return build_reflections(
        agent_name=agent_name,
        current_tick=0,
        supporting=supporting,
    )


def _specs_to_plan(specs: list[PlanItemSpec], *, start_tick: int) -> list[PlanItem]:
    plan: list[PlanItem] = []
    current = start_tick
    for spec in specs:
        duration = max(1, spec.duration)
        plan.append(
            PlanItem(
                start_tick=current,
                end_tick=current + duration,
                location=spec.location,
                description=spec.description,
            )
        )
        current += duration
    return plan


def _map_supports_to_links(supports: list[int], records) -> list[str]:
    links: list[str] = []
    for index in supports:
        if 1 <= index <= len(records):
            links.append(records[index - 1].record_id)
    return links


def _visible_agents(world, agent) -> list[str]:
    visible = []
    for node in world.nodes.values():
        if node.type == "agent" and node.parent_id == agent.location_id:
            if node.id != agent.agent_id:
                visible.append(node.name)
    return visible


def _visible_objects(world, agent) -> list[str]:
    visible = []
    for node in world.nodes.values():
        if node.type == "object" and node.parent_id == agent.location_id:
            visible.append(node.name)
    return visible
