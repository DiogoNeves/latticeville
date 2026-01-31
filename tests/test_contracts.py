from latticeville.sim.contracts import (
    ActionKind,
    BeliefTree,
    Event,
    StateSnapshot,
    TickPayload,
    ValidTargets,
    WorldNode,
    WorldTree,
    coerce_action,
)


def build_world_tree() -> WorldTree:
    nodes = {
        "world": WorldNode(
            id="world", name="World", type="area", parent_id=None, children=["room"]
        ),
        "room": WorldNode(
            id="room", name="Room", type="area", parent_id="world", children=["agent"]
        ),
        "agent": WorldNode(
            id="agent", name="Ada", type="agent", parent_id="room", children=[]
        ),
    }
    return WorldTree(root_id="world", nodes=nodes)


def test_world_and_belief_tree_shape() -> None:
    world = build_world_tree()
    belief_nodes = {
        "world": WorldNode(
            id="world", name="World", type="area", parent_id=None, children=["room"]
        ),
        "room": WorldNode(
            id="room", name="Room", type="area", parent_id="world", children=[]
        ),
    }
    belief = BeliefTree(root_id="world", nodes=belief_nodes)

    assert world.root_id == "world"
    assert "agent" in world.nodes
    assert belief.root_id == "world"
    assert "agent" not in belief.nodes


def test_action_coerce_and_targets() -> None:
    action = coerce_action({"kind": "MOVE", "move": {"to_location_id": "room"}})
    assert action.kind == ActionKind.MOVE

    invalid_kind = coerce_action({"kind": "FLY", "move": {"to_location_id": "room"}})
    assert invalid_kind.kind == ActionKind.IDLE

    invalid_args = coerce_action({"kind": "IDLE", "move": {"to_location_id": "room"}})
    assert invalid_args.kind == ActionKind.IDLE

    targets = ValidTargets(locations={"room"}, objects=set(), agents={"agent"})
    valid = coerce_action(
        {"kind": "MOVE", "move": {"to_location_id": "room"}},
        valid_targets=targets,
    )
    assert valid.kind == ActionKind.MOVE

    invalid_target = coerce_action(
        {"kind": "SAY", "say": {"to_agent_id": "other", "utterance": "hi"}},
        valid_targets=targets,
    )
    assert invalid_target.kind == ActionKind.IDLE


def test_tick_payload_events() -> None:
    world = build_world_tree()
    state = StateSnapshot(world=world, beliefs={})
    events = [Event(kind="MOVE", payload={"agent_id": "agent", "to": "room"})]
    payload = TickPayload(tick=1, state=state, events=events)

    assert payload.tick == 1
    assert payload.events is not None
    assert payload.events[0].kind == "MOVE"
