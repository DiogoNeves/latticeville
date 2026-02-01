from latticeville.sim.world_loader import load_world_config, load_world_state


def test_world_loader_parses_config() -> None:
    config = load_world_config()
    assert config.rooms
    assert config.characters
    assert config.map_file


def test_world_state_includes_rooms() -> None:
    state = load_world_state()
    assert state.rooms
    assert state.world_map.width > 0
    assert state.world_map.height > 0
