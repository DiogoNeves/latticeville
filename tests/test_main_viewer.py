from rich.console import Console

from latticeville.render.main_viewer import MainViewerState, render_main_view
from latticeville.sim.tick_loop import run_ticks
from latticeville.sim.world_state import build_tiny_world


def test_main_viewer_renders() -> None:
    state = build_tiny_world()
    payload = next(iter(run_ticks(state, ticks=1)))
    renderable = render_main_view(payload)

    console = Console(width=100, record=True)
    console.print(renderable)
    output = console.export_text()
    assert "Speech" in output
    assert "World:" in output
    assert "Characters" in output


def test_main_viewer_renders_overview() -> None:
    state = build_tiny_world()
    payload = next(iter(run_ticks(state, ticks=1)))
    view_state = MainViewerState(view_mode="overview")
    renderable = render_main_view(payload, state=view_state)

    console = Console(width=100, record=True)
    console.print(renderable)
    output = console.export_text()
    assert "World: overview" in output
