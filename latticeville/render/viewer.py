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


def render_tick(payload: TickPayload, *, max_events: int = 5) -> RenderableType:
    header = Text(f"Tick {payload.tick}", style="bold")
    locations = _render_locations(payload)
    events = _render_events(payload, max_events=max_events)
    belief = _render_belief_summary(payload)

    left = Group(header, locations, events)
    right = Group(belief)
    layout = Columns([Panel(left, title="Simulation"), Panel(right, title="Belief")])
    return layout


def _render_locations(payload: TickPayload) -> RenderableType:
    table = Table(title="Agent Locations", show_header=True, header_style="bold")
    table.add_column("Agent")
    table.add_column("Location")

    for node in payload.state.world.nodes.values():
        if node.type != "agent":
            continue
        location = payload.state.world.nodes.get(node.parent_id or "")
        table.add_row(node.name, location.name if location else "Unknown")
    return table


def _render_events(payload: TickPayload, *, max_events: int) -> RenderableType:
    table = Table(title="Recent Events", show_header=True, header_style="bold")
    table.add_column("Kind")
    table.add_column("Detail")

    events = list(payload.events or [])
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


def _collect_area_names(nodes: Iterable) -> list[str]:
    names = [node.name for node in nodes if node.type == "area"]
    counts = Counter(names)
    return sorted(counts.keys())


def _format_payload(payload: dict) -> str:
    if not payload:
        return "-"
    return ", ".join(f"{key}={value}" for key, value in payload.items())
