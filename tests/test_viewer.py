from rich.console import Console

from latticeville.render.viewer import render_tick
from latticeville.sim.contracts import (
    Event,
    StateSnapshot,
    TickPayload,
    WorldNode,
    WorldTree,
)


def test_render_tick_contains_expected_sections() -> None:
    nodes = {
        "world": WorldNode(
            id="world", name="World", type="area", parent_id=None, children=["street"]
        ),
        "street": WorldNode(
            id="street", name="Street", type="area", parent_id="world", children=["ada"]
        ),
        "ada": WorldNode(
            id="ada", name="Ada", type="agent", parent_id="street", children=[]
        ),
    }
    world = WorldTree(root_id="world", nodes=nodes)
    payload = TickPayload(
        tick=3,
        state=StateSnapshot(world=world, beliefs={}),
        events=[Event(kind="MOVE", payload={"agent_id": "ada", "to": "street"})],
    )

    console = Console(width=80, record=True)
    console.print(render_tick(payload))
    output = console.export_text()

    assert "Tick 3" in output
    assert "Agent Locations" in output
    assert "Recent Events" in output
    assert "Belief Summary" in output
    assert "Memory Summary" in output
    assert "Ada" in output
    assert "MOVE" in output


def test_render_tick_without_events_or_beliefs() -> None:
    nodes = {
        "world": WorldNode(
            id="world", name="World", type="area", parent_id=None, children=["street"]
        ),
        "street": WorldNode(
            id="street", name="Street", type="area", parent_id="world", children=["ada"]
        ),
        "ada": WorldNode(
            id="ada", name="Ada", type="agent", parent_id="street", children=[]
        ),
    }
    world = WorldTree(root_id="world", nodes=nodes)
    payload = TickPayload(
        tick=1,
        state=StateSnapshot(world=world, beliefs={}),
        events=None,
    )

    console = Console(width=80, record=True)
    console.print(render_tick(payload))
    output = console.export_text()

    assert "None" in output
    assert "Memory Summary" in output
