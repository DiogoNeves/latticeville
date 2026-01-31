import json
from pathlib import Path

from latticeville.db.replay_log import (
    RUN_LOG_NAME,
    append_tick_payload,
    create_run_folder,
    write_header,
)
from latticeville.render.replay_reader import read_tick_payloads
from latticeville.sim.contracts import StateSnapshot, TickPayload, WorldNode, WorldTree


def test_replay_log_header_and_ticks(tmp_path: Path) -> None:
    run_dir, log_path = create_run_folder(tmp_path, timestamp="2026-01-31T15-50-00Z")
    write_header(log_path, metadata={"run_id": run_dir.name})

    world = _build_world()
    payload = TickPayload(tick=1, state=StateSnapshot(world=world, beliefs={}))
    append_tick_payload(log_path, payload)

    with log_path.open("r", encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle]

    assert log_path.name == RUN_LOG_NAME
    assert records[0]["type"] == "header"
    assert records[0]["metadata"]["run_id"] == run_dir.name
    assert records[1]["type"] == "tick"
    assert records[1]["payload"]["tick"] == 1


def test_replay_reader_skips_header(tmp_path: Path) -> None:
    run_dir, log_path = create_run_folder(tmp_path, timestamp="2026-01-31T15-51-00Z")
    write_header(log_path, metadata={"run_id": run_dir.name})

    world = _build_world()
    payload = TickPayload(tick=2, state=StateSnapshot(world=world, beliefs={}))
    append_tick_payload(log_path, payload)

    payloads = list(read_tick_payloads(log_path))
    assert len(payloads) == 1
    assert payloads[0].tick == 2


def _build_world() -> WorldTree:
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
    return WorldTree(root_id="world", nodes=nodes)
