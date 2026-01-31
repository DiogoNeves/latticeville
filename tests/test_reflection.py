from latticeville.sim.reflection import ReflectionState, build_reflections
from latticeville.sim.memory import MemoryRecord


def test_reflection_state_threshold() -> None:
    state = ReflectionState(threshold=10.0)
    state.record_importance(3.0)
    state.record_importance(7.0)
    assert state.should_reflect()
    state.reset()
    assert not state.should_reflect()


def test_build_reflections_links() -> None:
    records = [
        MemoryRecord(
            description=f"Memory {index}",
            created_at=1,
            last_accessed_at=1,
            importance=1.0,
            type="observation",
        )
        for index in range(5)
    ]
    insights = build_reflections(
        agent_name="Ada",
        current_tick=2,
        supporting=records,
    )
    assert len(insights) >= 1
    assert insights[0][1]
