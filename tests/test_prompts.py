from latticeville.llm.fake_llm import FakeLLM
from latticeville.llm.prompt_fixtures import fixture_for
from latticeville.llm.prompts import (
    DayPlanInput,
    ObservationInput,
    PlanDecomposeInput,
    PromptId,
    ReactInput,
    parse_prompt_output,
    render_prompt,
)


def test_observation_fixture_parses() -> None:
    payload = ObservationInput(
        agent_name="Ada",
        location_name="Street",
        visible_agents=["Lin"],
        visible_objects=["Bench"],
    )
    text = fixture_for(PromptId.OBSERVATION, payload)
    output = parse_prompt_output(PromptId.OBSERVATION, text)
    assert output is not None
    assert output.observations
    assert "Ada" in output.observations[0]


def test_day_plan_fixture_parses() -> None:
    payload = DayPlanInput(agent_name="Ada", start_tick=1, context=None)
    text = fixture_for(PromptId.DAY_PLAN, payload)
    output = parse_prompt_output(PromptId.DAY_PLAN, text)
    assert output is not None
    assert len(output.items) >= 3


def test_plan_decompose_fixture_splits() -> None:
    payload = PlanDecomposeInput(
        items=[
            {"description": "Test", "location": "street", "duration": 3},
        ],
        chunk_size=1,
    )
    text = fixture_for(PromptId.PLAN_DECOMPOSE, payload)
    output = parse_prompt_output(PromptId.PLAN_DECOMPOSE, text)
    assert output is not None
    assert len(output.items) == 3


def test_fake_llm_complete_prompt_uses_fixture() -> None:
    policy = FakeLLM()
    payload = ReactInput(
        agent_name="Ada", observation="Saw a friend.", current_plan="Keep walking."
    )
    prompt = render_prompt(PromptId.REACT, payload)
    response = policy.complete_prompt(prompt_id=PromptId.REACT.value, prompt=prompt)
    output = parse_prompt_output(PromptId.REACT, response)
    assert output is not None
    assert output.react is False
