"""Reflection trigger and insight generation."""

from __future__ import annotations

from dataclasses import dataclass

from latticeville.sim.memory import MemoryRecord


@dataclass
class ReflectionState:
    threshold: float = 10.0
    since_last: float = 0.0

    def record_importance(self, importance: float) -> None:
        self.since_last += importance

    def should_reflect(self) -> bool:
        return self.since_last >= self.threshold

    def reset(self) -> None:
        self.since_last = 0.0


def build_reflections(
    *,
    agent_name: str,
    current_tick: int,
    supporting: list[MemoryRecord],
) -> list[tuple[str, list[str]]]:
    if not supporting:
        return []
    insights = [
        (
            f"{agent_name} noticed a pattern in recent events.",
            [record.record_id for record in supporting[:2]],
        ),
        (
            f"{agent_name} is forming a short-term routine.",
            [record.record_id for record in supporting[2:4]],
        ),
        (
            f"{agent_name} should follow through on recent observations.",
            [record.record_id for record in supporting[-2:]],
        ),
    ]
    return insights
