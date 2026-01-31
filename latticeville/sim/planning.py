"""Planning helpers for Phase 6."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class PlanItem:
    start_tick: int
    end_tick: int
    location: str
    description: str


def build_day_plan(agent_name: str, *, start_tick: int) -> list[PlanItem]:
    day_chunks = [
        ("street", f"{agent_name} starts the day and checks the surroundings."),
        ("cafe", f"{agent_name} spends time at the cafe and observes activity."),
        ("park", f"{agent_name} takes a short walk and reflects."),
        ("street", f"{agent_name} does a short errand and returns."),
        ("cafe", f"{agent_name} wraps up with a final stop at the cafe."),
    ]
    duration = 4
    plan: list[PlanItem] = []
    current = start_tick
    for location, description in day_chunks:
        plan.append(
            PlanItem(
                start_tick=current,
                end_tick=current + duration,
                location=location,
                description=description,
            )
        )
        current += duration
    return plan


def decompose_to_hours(plan: Iterable[PlanItem]) -> list[PlanItem]:
    return _decompose(plan, chunk_size=1, suffix="(hour chunk)")


def decompose_to_actions(plan: Iterable[PlanItem]) -> list[PlanItem]:
    return _decompose(plan, chunk_size=1, suffix="(action slice)")


def _decompose(
    plan: Iterable[PlanItem], *, chunk_size: int, suffix: str
) -> list[PlanItem]:
    decomposed: list[PlanItem] = []
    for item in plan:
        current = item.start_tick
        while current < item.end_tick:
            end_tick = min(current + chunk_size, item.end_tick)
            decomposed.append(
                PlanItem(
                    start_tick=current,
                    end_tick=end_tick,
                    location=item.location,
                    description=f"{item.description} {suffix}",
                )
            )
            current = end_tick
    return decomposed
