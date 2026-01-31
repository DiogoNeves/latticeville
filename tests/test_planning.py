from latticeville.sim.planning import build_day_plan, decompose_to_actions


def test_day_plan_and_decomposition_counts() -> None:
    plan = build_day_plan("Ada", start_tick=0)
    assert 5 <= len(plan) <= 8

    actions = decompose_to_actions(plan)
    assert len(actions) >= len(plan)

    first = actions[0]
    assert first.start_tick == 0
    assert first.end_tick > first.start_tick
