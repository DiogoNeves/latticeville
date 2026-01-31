from latticeville.sim.movement import build_area_graph
from latticeville.sim.world_loader import load_world_config, load_world_state


def test_world_loader_parses_config() -> None:
    config = load_world_config()
    assert config.areas
    assert config.characters


def test_world_state_includes_portals() -> None:
    state = load_world_state()
    assert "street" in state.portals
    assert state.portals["street"]


def test_portal_graph_links_areas() -> None:
    state = load_world_state()
    graph = build_area_graph(state.world, portals=state.portals)
    assert "street" in graph
    assert "cafe" in graph["street"]
