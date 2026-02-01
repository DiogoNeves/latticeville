"""Planning helpers for Phase 6."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4
from typing import Iterable


@dataclass(frozen=True)
class PlanItem:
    plan_id: str
    start_tick: int
    end_tick: int
    location: str
    description: str
    level: str = "action"
    parent_id: str | None = None


@dataclass(frozen=True)
class PlanHierarchy:
    day: list[PlanItem]
    hours: list[PlanItem]
    actions: list[PlanItem]


TICK_MINUTES = 10
TICKS_PER_HOUR = 60 // TICK_MINUTES
DAY_START_HOUR = 8


def tick_to_time(
    tick: int, *, start_hour: int = DAY_START_HOUR, tick_minutes: int = TICK_MINUTES
) -> str:
    total_minutes = (start_hour * 60) + (tick * tick_minutes)
    total_minutes %= 24 * 60
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours:02d}:{minutes:02d}"


def format_time_window(
    start_tick: int,
    end_tick: int,
    *,
    start_hour: int = DAY_START_HOUR,
    tick_minutes: int = TICK_MINUTES,
) -> str:
    start = tick_to_time(start_tick, start_hour=start_hour, tick_minutes=tick_minutes)
    end = tick_to_time(end_tick, start_hour=start_hour, tick_minutes=tick_minutes)
    return f"{start}-{end}"


def _new_plan_id() -> str:
    return uuid4().hex


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
                plan_id=_new_plan_id(),
                start_tick=current,
                end_tick=current + duration,
                location=location,
                description=description,
                level="day",
            )
        )
        current += duration
    return plan


def decompose_to_hours(plan: Iterable[PlanItem]) -> list[PlanItem]:
    return _decompose(
        plan,
        chunk_size=TICKS_PER_HOUR,
        level="hour",
        suffix="(hour chunk)",
    )


def decompose_to_actions(plan: Iterable[PlanItem]) -> list[PlanItem]:
    return _decompose(plan, chunk_size=1, level="action", suffix="(action slice)")


def _decompose(
    plan: Iterable[PlanItem], *, chunk_size: int, level: str, suffix: str
) -> list[PlanItem]:
    decomposed: list[PlanItem] = []
    for item in plan:
        current = item.start_tick
        while current < item.end_tick:
            end_tick = min(current + chunk_size, item.end_tick)
            decomposed.append(
                PlanItem(
                    plan_id=_new_plan_id(),
                    start_tick=current,
                    end_tick=end_tick,
                    location=item.location,
                    description=f"{item.description} {suffix}",
                    level=level,
                    parent_id=item.plan_id,
                )
            )
            current = end_tick
    return decomposed
