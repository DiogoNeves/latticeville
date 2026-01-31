"""Tick loop orchestration for the minimal simulator."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from latticeville.db.memory_log import append_memory_record
from latticeville.llm.base import LLMPolicy, build_valid_targets
from latticeville.llm.embedder import Embedder, FakeEmbedder
from latticeville.llm.fake_llm import FakeLLM
from latticeville.sim.contracts import ActionKind, Event, StateSnapshot, TickPayload
from latticeville.sim.memory import MemoryStream
from latticeville.sim.movement import advance_movement, start_move
from latticeville.sim.world_state import WorldState


def run_ticks(
    state: WorldState,
    ticks: int,
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
    for _ in range(ticks):
        world_snapshot = state.world.model_copy(deep=True)
        snapshot_locations = {
            agent_id: agent.location_id for agent_id, agent in state.agents.items()
        }

        actions = {}
        for agent_id in sorted(state.agents.keys()):
            agent = state.agents[agent_id]
            agent.location_id = snapshot_locations[agent_id]
            valid_targets = build_valid_targets(world_snapshot, agent=agent)
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
            start_move(agent, state.world, action.move.to_location_id)

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
            location_node = state.world.nodes.get(agent.location_id)
            location_name = location_node.name if location_node else agent.location_id
            observation = f"{agent.name} is at {location_name}."
            record = stream.append(
                description=observation,
                created_at=tick_id,
                importance=1.0,
                type="observation",
            )
            if memory_log_path:
                append_memory_record(memory_log_path, agent_id=agent_id, record=record)

            move_event = move_events_by_agent.get(agent_id)
            if move_event:
                move_desc = (
                    f"{agent.name} moved from {move_event.payload.get('from')} "
                    f"to {move_event.payload.get('to')}."
                )
                move_record = stream.append(
                    description=move_desc,
                    created_at=tick_id,
                    importance=2.0,
                    type="action",
                )
                if memory_log_path:
                    append_memory_record(
                        memory_log_path,
                        agent_id=agent_id,
                        record=move_record,
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

        events.extend(memory_events)
        state.tick += 1
        world_snapshot = state.world.model_copy(deep=True)
        payload = TickPayload(
            tick=state.tick,
            state=StateSnapshot(world=world_snapshot, beliefs={}),
            events=events or None,
        )
        yield payload
