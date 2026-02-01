from latticeville.llm.base import build_valid_targets
from latticeville.llm.fake_llm import FakeLLM
from latticeville.sim.contracts import ActionKind, WorldNode, WorldTree
from latticeville.sim.world_state import AgentState


def test_fake_llm_deterministic_move() -> None:
    world = _build_world()
    agent = AgentState(
        agent_id="ada",
        name="Ada",
        location_id="street",
        position=(1, 1),
        patrol_route=["street", "cafe"],
    )
    policy = FakeLLM()
    targets = build_valid_targets(world, agent=agent)

    first = policy.decide_action(world=world, agent=agent, valid_targets=targets)
    second = policy.decide_action(world=world, agent=agent, valid_targets=targets)

    assert first.kind == ActionKind.MOVE
    assert first == second


def test_fake_llm_invalid_target_falls_back_to_idle() -> None:
    world = _build_world()
    agent = AgentState(
        agent_id="ada",
        name="Ada",
        location_id="street",
        position=(1, 1),
        patrol_route=["street", "nowhere"],
    )
    policy = FakeLLM()
    targets = build_valid_targets(world, agent=agent)

    action = policy.decide_action(world=world, agent=agent, valid_targets=targets)
    assert action.kind == ActionKind.IDLE


def _build_world() -> WorldTree:
    nodes = {
        "world": WorldNode(
            id="world", name="World", type="area", parent_id=None, children=["street"]
        ),
        "street": WorldNode(
            id="street",
            name="Street",
            type="area",
            parent_id="world",
            children=["cafe", "ada"],
        ),
        "cafe": WorldNode(
            id="cafe", name="Cafe", type="area", parent_id="street", children=[]
        ),
        "ada": WorldNode(
            id="ada", name="Ada", type="agent", parent_id="street", children=[]
        ),
    }
    return WorldTree(root_id="world", nodes=nodes)
