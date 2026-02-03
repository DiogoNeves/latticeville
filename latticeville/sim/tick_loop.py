"""Tick loop orchestration for the minimal simulator."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4
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
    summarize_statements,
)
from latticeville.sim.contracts import ActionKind, Event, StateSnapshot, TickPayload
from latticeville.sim.memory import MemoryStream
from latticeville.sim.movement import advance_movement, build_grid, start_move
from latticeville.sim.pathfinding import PathFinder
from latticeville.sim.planning import (
    PlanHierarchy,
    PlanItem,
    TICKS_PER_HOUR,
    build_day_plan,
    decompose_to_actions,
    decompose_to_hours,
    format_time_window,
)
from latticeville.sim.reflection import ReflectionState, build_reflections
from latticeville.sim.world_state import WorldState
from latticeville.sim.world_utils import resolve_area_id


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
    plan_cache: dict[str, PlanHierarchy] = {}
    dialogue_histories: dict[tuple[str, str], list[str]] = {}
    pathfinder = PathFinder(build_grid(state.world_map))
    step_count = 0
    while ticks is None or step_count < ticks:
        world_snapshot = state.world.model_copy(deep=True)
        snapshot_locations = {
            agent_id: agent.location_id for agent_id, agent in state.agents.items()
        }
        tick_id = state.tick + 1

        actions = {}
        plan_steps: dict[str, str | None] = {}
        for agent_id in sorted(state.agents.keys()):
            agent = state.agents[agent_id]
            agent.location_id = snapshot_locations[agent_id]
            valid_targets = build_valid_targets(world_snapshot, agent=agent)
            plan_step = None
            if agent_id in plan_cache:
                for item in plan_cache[agent_id].actions:
                    if item.start_tick <= tick_id < item.end_tick:
                        plan_step = item.description
                        break
            plan_steps[agent_id] = plan_step
            actions[agent_id] = llm_policy.decide_action(
                world=world_snapshot,
                agent=agent,
                valid_targets=valid_targets,
                plan_step=plan_step,
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
                state,
                action.move.to_location_id,
                pathfinder=pathfinder,
            )

        events: list[Event] = []
        move_events_by_agent: dict[str, Event] = {}
        for agent_id in sorted(state.agents.keys()):
            agent = state.agents[agent_id]
            event = advance_movement(state, agent)
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
            location_name = (
                location_node.name if location_node else agent.location_id or "Unknown"
            )
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
                target_id = action.say.to_agent_id
                target_name = (
                    state.agents[target_id].name
                    if target_id in state.agents
                    else target_id
                )
                history = _dialogue_history(
                    dialogue_histories,
                    agent_id=agent_id,
                    target_agent_id=target_id,
                )
                recent_memories = summarize_statements(
                    [record.description for record in stream.records[-5:]],
                    limit=5,
                )
                plan_context = plan_steps.get(agent_id)
                utterance = _generate_dialogue(
                    llm_policy,
                    agent_name=agent.name,
                    target_agent_id=target_id,
                    observation=f"{agent.name} is initiating a conversation.",
                    history=history,
                    context=_dialogue_context(
                        agent_name=agent.name,
                        target_agent_name=target_name,
                        observation=observations[0] if observations else "",
                        memory_context=recent_memories,
                        plan_context=plan_context,
                    ),
                )
                if utterance:
                    action.say.utterance = utterance
                    _record_dialogue(
                        dialogue_histories,
                        agent_id=agent_id,
                        agent_name=agent.name,
                        target_agent_id=target_id,
                        target_agent_name=target_name,
                        utterance=utterance,
                    )
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
                hierarchy = _build_plan_hierarchy(
                    llm_policy, agent.name, tick_id, context=None
                )
                plan_cache[agent_id] = hierarchy
                for item in hierarchy.day:
                    plan_text = _plan_memory_text(item)
                    plan_importance = _score_importance(
                        llm_policy,
                        memory_text=plan_text,
                        memory_type="plan",
                    )
                    plan_record = stream.append(
                        description=plan_text,
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

            active_plan = _active_plan(plan_cache[agent_id].actions, tick_id)
            if active_plan:
                memory_events.append(
                    Event(
                        kind="PLAN_SUMMARY",
                        payload={
                            "agent_id": agent_id,
                            "start_tick": active_plan.start_tick,
                            "end_tick": active_plan.end_tick,
                            "time_window": format_time_window(
                                active_plan.start_tick, active_plan.end_tick
                            ),
                            "location": active_plan.location,
                            "description": active_plan.description,
                            "level": active_plan.level,
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
                hierarchy = _build_plan_hierarchy(
                    llm_policy,
                    agent.name,
                    tick_id,
                    context=react_output.reaction,
                )
                plan_cache[agent_id] = hierarchy
                for item in hierarchy.day:
                    plan_text = _plan_memory_text(item)
                    plan_importance = _score_importance(
                        llm_policy,
                        memory_text=plan_text,
                        memory_type="plan",
                    )
                    plan_record = stream.append(
                        description=plan_text,
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
                reflection_state.reset()
                for description, links in insights:
                    reflection_importance = _score_importance(
                        llm_policy,
                        memory_text=description,
                        memory_type="reflection",
                    )
                    reflection_state.record_importance(reflection_importance)
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
        agent_positions = {
            agent_id: agent.position for agent_id, agent in state.agents.items()
        }
        payload = TickPayload(
            tick=state.tick,
            state=StateSnapshot(
                world=world_snapshot,
                beliefs={},
                agent_positions=agent_positions,
            ),
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
        return _specs_to_plan(specs, start_tick=start_tick, level="day")
    return build_day_plan(agent_name, start_tick=start_tick)


def _decompose_plan(
    policy: LLMPolicy,
    plan: list[PlanItem],
    *,
    chunk_size: int,
    level: str,
) -> list[PlanItem]:
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
        PlanDecomposeInput(items=specs, chunk_size=chunk_size),
    )
    if output and getattr(output, "items", None):
        decomposed_specs = [PlanItemSpec.model_validate(item) for item in output.items]
        return _specs_to_plan(
            decomposed_specs,
            start_tick=plan[0].start_tick,
            level=level,
            parent_plan=plan,
        )
    fallback = (
        decompose_to_hours(plan) if level == "hour" else decompose_to_actions(plan)
    )
    return _assign_parent_ids(fallback, plan)


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
    history: list[str],
    context: str | None,
) -> str | None:
    output = _run_prompt(
        policy,
        PromptId.DIALOGUE_INITIATOR,
        DialogueInput(
            agent_name=agent_name,
            observation=observation,
            context=context or f"Speaking to {target_agent_id}.",
            history=history,
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


def _specs_to_plan(
    specs: list[PlanItemSpec],
    *,
    start_tick: int,
    level: str,
    parent_plan: list[PlanItem] | None = None,
) -> list[PlanItem]:
    plan: list[PlanItem] = []
    current = start_tick
    for spec in specs:
        duration = max(1, spec.duration)
        parent_id = _parent_id_for_tick(parent_plan, current)
        plan.append(
            PlanItem(
                plan_id=_new_plan_id(),
                start_tick=current,
                end_tick=current + duration,
                location=spec.location,
                description=spec.description,
                level=level,
                parent_id=parent_id,
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


def _build_plan_hierarchy(
    policy: LLMPolicy,
    agent_name: str,
    start_tick: int,
    *,
    context: str | None,
) -> PlanHierarchy:
    day_plan = _build_day_plan(
        policy, agent_name=agent_name, start_tick=start_tick, context=context
    )
    if not day_plan:
        return PlanHierarchy(day=[], hours=[], actions=[])
    hour_plan = _decompose_plan(
        policy, day_plan, chunk_size=TICKS_PER_HOUR, level="hour"
    )
    if not hour_plan:
        return PlanHierarchy(day=day_plan, hours=[], actions=[])
    action_plan = _decompose_plan(policy, hour_plan, chunk_size=1, level="action")
    return PlanHierarchy(day=day_plan, hours=hour_plan, actions=action_plan)


def _active_plan(plan: list[PlanItem], tick_id: int) -> PlanItem | None:
    for item in plan:
        if item.start_tick <= tick_id < item.end_tick:
            return item
    return None


def _plan_memory_text(item: PlanItem) -> str:
    window = format_time_window(item.start_tick, item.end_tick)
    return f"[{item.level}] {item.description} ({window} @ {item.location})"


def _new_plan_id() -> str:
    return uuid4().hex


def _parent_id_for_tick(parent_plan: list[PlanItem] | None, tick_id: int) -> str | None:
    if not parent_plan:
        return None
    for parent in parent_plan:
        if parent.start_tick <= tick_id < parent.end_tick:
            return parent.plan_id
    return None


def _assign_parent_ids(
    plan: list[PlanItem], parent_plan: list[PlanItem]
) -> list[PlanItem]:
    if not parent_plan:
        return plan
    updated: list[PlanItem] = []
    for item in plan:
        parent_id = _parent_id_for_tick(parent_plan, item.start_tick)
        if parent_id == item.parent_id:
            updated.append(item)
        else:
            updated.append(
                PlanItem(
                    plan_id=item.plan_id,
                    start_tick=item.start_tick,
                    end_tick=item.end_tick,
                    location=item.location,
                    description=item.description,
                    level=item.level,
                    parent_id=parent_id,
                )
            )
    return updated


def _visible_agents(world, agent) -> list[str]:
    visible = []
    agent_area = resolve_area_id(world, agent.location_id) or agent.location_id
    for node in world.nodes.values():
        if node.type == "agent" and resolve_area_id(world, node.id) == agent_area:
            if node.id != agent.agent_id:
                visible.append(node.name)
    return visible


def _visible_objects(world, agent) -> list[str]:
    visible = []
    agent_area = resolve_area_id(world, agent.location_id) or agent.location_id
    for node in world.nodes.values():
        if node.type == "object" and resolve_area_id(world, node.id) == agent_area:
            visible.append(node.name)
    return visible


def _dialogue_key(agent_id: str, target_agent_id: str) -> tuple[str, str]:
    return tuple(sorted((agent_id, target_agent_id)))


def _dialogue_history(
    histories: dict[tuple[str, str], list[str]],
    *,
    agent_id: str,
    target_agent_id: str,
    limit: int = 6,
) -> list[str]:
    history = histories.get(_dialogue_key(agent_id, target_agent_id), [])
    if len(history) <= limit:
        return list(history)
    return list(history[-limit:])


def _record_dialogue(
    histories: dict[tuple[str, str], list[str]],
    *,
    agent_id: str,
    agent_name: str,
    target_agent_id: str,
    target_agent_name: str,
    utterance: str,
    limit: int = 12,
) -> None:
    _ = target_agent_name
    key = _dialogue_key(agent_id, target_agent_id)
    history = histories.setdefault(key, [])
    history.append(f"{agent_name}: {utterance}")
    if len(history) > limit:
        histories[key] = history[-limit:]


def _dialogue_context(
    *,
    agent_name: str,
    target_agent_name: str,
    observation: str,
    memory_context: str,
    plan_context: str | None,
) -> str:
    parts = []
    if observation:
        parts.append(f"Observation: {observation}")
    if memory_context:
        parts.append(f"Recent memories: {memory_context}")
    if plan_context:
        parts.append(f"Current plan: {plan_context}")
    parts.append(f"Speaking to {target_agent_name}.")
    return " ".join(parts)
