"""Rich viewer rendering for TickPayload."""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from rich.columns import Columns
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from latticeville.sim.contracts import TickPayload
from latticeville.sim.world_utils import resolve_area_name


def render_tick(payload: TickPayload, *, max_events: int = 5) -> RenderableType:
    header = Text(f"Tick {payload.tick}", style="bold")
    locations = _render_locations(payload)
    events = _render_events(payload, max_events=max_events)
    belief = _render_belief_summary(payload)
    memory = _render_memory_summary(payload)
    plan = _render_plan_summary(payload)
    reflections = _render_reflection_summary(payload)

    left = Group(header, locations, events)
    right = Group(belief, memory, plan, reflections)
    layout = Columns([Panel(left, title="Simulation"), Panel(right, title="Belief")])
    return layout


def _render_locations(payload: TickPayload) -> RenderableType:
    table = Table(title="Agent Locations", show_header=True, header_style="bold")
    table.add_column("Agent")
    table.add_column("Location")

    for node in payload.state.world.nodes.values():
        if node.type != "agent":
            continue
        location = resolve_area_name(payload.state.world, node.id)
        table.add_row(node.name, location or "Unknown")
    return table


def _render_events(payload: TickPayload, *, max_events: int) -> RenderableType:
    table = Table(title="Recent Events", show_header=True, header_style="bold")
    table.add_column("Kind")
    table.add_column("Detail")

    events = [
        event for event in (payload.events or []) if event.kind != "MEMORY_SUMMARY"
    ]
    for event in events[-max_events:]:
        table.add_row(event.kind, _format_payload(event.payload))
    if not events:
        table.add_row("-", "None")
    return table


def _render_belief_summary(payload: TickPayload) -> RenderableType:
    if not payload.state.beliefs:
        return Panel(Text("No belief data available."), title="Belief Summary")

    agent_id, belief = next(iter(payload.state.beliefs.items()))
    area_names = _collect_area_names(belief.nodes.values())
    summary = Table(show_header=False)
    summary.add_column("Field")
    summary.add_column("Value")
    summary.add_row("Agent", agent_id)
    summary.add_row("Known areas", ", ".join(area_names) or "None")
    summary.add_row("Known nodes", str(len(belief.nodes)))
    return Panel(summary, title="Belief Summary")


def _render_memory_summary(payload: TickPayload) -> RenderableType:
    summaries = [
        event.payload
        for event in (payload.events or [])
        if event.kind == "MEMORY_SUMMARY"
    ]
    if not summaries:
        return Panel(Text("No memory data available."), title="Memory Summary")

    summary = sorted(summaries, key=lambda item: item.get("agent_id", ""))[0]
    table = Table(show_header=False)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Agent", summary.get("agent_id", ""))
    table.add_row("Total", str(summary.get("total", 0)))
    latest = summary.get("latest", [])
    retrieved = summary.get("retrieved", [])
    table.add_row("Latest", "; ".join(latest) if latest else "None")
    table.add_row("Retrieved", "; ".join(retrieved) if retrieved else "None")
    return Panel(table, title="Memory Summary")


def _render_plan_summary(payload: TickPayload) -> RenderableType:
    summaries = [
        event.payload
        for event in (payload.events or [])
        if event.kind == "PLAN_SUMMARY"
    ]
    if not summaries:
        return Panel(Text("No plan data available."), title="Plan Summary")
    summary = sorted(summaries, key=lambda item: item.get("agent_id", ""))[0]
    table = Table(show_header=False)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Agent", summary.get("agent_id", ""))
    time_window = summary.get("time_window")
    if time_window:
        table.add_row("Window", time_window)
    else:
        table.add_row(
            "Window", f"{summary.get('start_tick')}–{summary.get('end_tick')}"
        )
    table.add_row("Location", summary.get("location", ""))
    table.add_row("Description", summary.get("description", ""))
    return Panel(table, title="Plan Summary")


def _render_reflection_summary(payload: TickPayload) -> RenderableType:
    summaries = [
        event.payload
        for event in (payload.events or [])
        if event.kind == "REFLECTION_SUMMARY"
    ]
    if not summaries:
        return Panel(Text("No reflections yet."), title="Reflection Summary")
    summary = sorted(summaries, key=lambda item: item.get("agent_id", ""))[0]
    table = Table(show_header=False)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Agent", summary.get("agent_id", ""))
    table.add_row("Count", str(summary.get("count", 0)))
    items = summary.get("items", [])
    table.add_row("Items", "; ".join(items) if items else "None")
    return Panel(table, title="Reflection Summary")


def _collect_area_names(nodes: Iterable) -> list[str]:
    names = [node.name for node in nodes if node.type == "area"]
    counts = Counter(names)
    return sorted(counts.keys())


def _format_payload(payload: dict) -> str:
    if not payload:
        return "-"
    return ", ".join(f"{key}={value}" for key, value in payload.items())
