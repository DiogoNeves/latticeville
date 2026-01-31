from latticeville.render.main_viewer import map_character_click


def test_map_character_click_selects_agent() -> None:
    hitboxes = [
        (1, 1, "ada"),
        (2, 1, "byron"),
    ]
    assert map_character_click(hitboxes, x=2, y=2) == "byron"
    assert map_character_click(hitboxes, x=2, y=1) == "ada"
    assert map_character_click(hitboxes, x=None, y=1) is None
    assert map_character_click(hitboxes, x=2, y=3) is None
