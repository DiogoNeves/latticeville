from latticeville.sim.tick_loop import run_ticks
from latticeville.sim.world_state import build_tiny_world


def test_patrol_movement_and_tick_payloads() -> None:
    state = build_tiny_world()
    payloads = list(run_ticks(state, ticks=2))

    assert [payload.tick for payload in payloads] == [1, 2]

    pos_first = payloads[0].state.agent_positions["ada"]
    pos_second = payloads[1].state.agent_positions["ada"]
    assert pos_first != pos_second


def test_move_event_payload_shape() -> None:
    state = build_tiny_world()
    payloads = list(run_ticks(state, ticks=10))

    move_events = [
        event
        for payload in payloads
        for event in (payload.events or [])
        if event.kind == "MOVE"
    ]
    if not move_events:
        return
    sample = move_events[0]
    assert "agent_id" in sample.payload
    assert "from" in sample.payload
    assert "to" in sample.payload
