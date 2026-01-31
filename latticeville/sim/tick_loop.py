"""Tick loop orchestration for the minimal simulator."""

from __future__ import annotations

from typing import Iterable

from latticeville.llm.base import LLMPolicy, build_valid_targets
from latticeville.llm.fake_llm import FakeLLM
from latticeville.sim.contracts import ActionKind, Event, StateSnapshot, TickPayload
from latticeville.sim.movement import advance_movement, start_move
from latticeville.sim.world_state import WorldState


def run_ticks(
    state: WorldState, ticks: int, *, policy: LLMPolicy | None = None
) -> Iterable[TickPayload]:
    llm_policy = policy or FakeLLM()
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
        for agent_id in sorted(state.agents.keys()):
            agent = state.agents[agent_id]
            event = advance_movement(state.world, agent)
            if event:
                events.append(event)
                if agent.travel_destination is None:
                    agent.set_route_index(agent.location_id)

        state.tick += 1
        world_snapshot = state.world.model_copy(deep=True)
        payload = TickPayload(
            tick=state.tick,
            state=StateSnapshot(world=world_snapshot, beliefs={}),
            events=events or None,
        )
        yield payload
