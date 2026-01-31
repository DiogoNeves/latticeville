from latticeville.sim.tick_loop import run_ticks
from latticeville.sim.world_state import build_tiny_world


def test_patrol_movement_and_tick_payloads() -> None:
    state = build_tiny_world()
    payloads = list(run_ticks(state, ticks=2))

    assert [payload.tick for payload in payloads] == [1, 2]

    assert payloads[0].state.world.nodes["ada"].parent_id == "cafe"
    assert payloads[1].state.world.nodes["ada"].parent_id == "park"


def test_intermediate_occupancy_and_event() -> None:
    state = build_tiny_world()
    payloads = list(run_ticks(state, ticks=2))

    first_events = [
        event
        for event in (payloads[0].events or [])
        if event.kind == "MOVE" and event.payload.get("agent_id") == "ada"
    ]
    second_events = [
        event
        for event in (payloads[1].events or [])
        if event.kind == "MOVE" and event.payload.get("agent_id") == "ada"
    ]

    assert len(first_events) == 0
    assert len(second_events) == 1
    assert second_events[0].kind == "MOVE"
    assert second_events[0].payload["agent_id"] == "ada"
