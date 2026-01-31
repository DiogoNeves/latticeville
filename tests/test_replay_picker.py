from pathlib import Path

from latticeville.db.replay_log import RUN_LOG_NAME
from latticeville.render.replay_picker import list_replay_runs, load_replay_payloads


def test_list_replay_runs(tmp_path: Path) -> None:
    run_dir = tmp_path / "2026-01-01T00-00-00Z"
    run_dir.mkdir()
    log_path = run_dir / RUN_LOG_NAME
    log_path.write_text(
        '{"type":"header","schema_version":1,'
        '"metadata":{"run_id":"2026-01-01T00-00-00Z","ticks":2}}\n',
        encoding="utf-8",
    )

    runs = list_replay_runs(tmp_path)
    assert runs
    assert runs[0].run_id == "2026-01-01T00-00-00Z"


def test_load_replay_payloads(tmp_path: Path) -> None:
    run_dir = tmp_path / "2026-01-01T00-00-00Z"
    run_dir.mkdir()
    log_path = run_dir / RUN_LOG_NAME
    log_path.write_text(
        '{"type":"header","schema_version":1,"metadata":{"run_id":"run","ticks":2}}\n'
        '{"type":"tick","schema_version":1,"payload":{"tick":1,'
        '"state":{"world":{"root_id":"world","nodes":{'
        '"world":{"id":"world","name":"World","type":"area","parent_id":null,"children":[]}'
        "}},"
        '"beliefs":{}},"events":null}}\n',
        encoding="utf-8",
    )
    payloads = load_replay_payloads(log_path)
    assert len(payloads) == 1
