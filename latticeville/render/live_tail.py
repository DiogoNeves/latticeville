"""Tail a JSONL replay log and render latest-frame output."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.live import Live

from latticeville.render.viewer import render_tick
from latticeville.sim.contracts import TickPayload


def tail_replay_log(path: Path, *, poll_interval: float = 0.2) -> None:
    console = Console()
    path.parent.mkdir(parents=True, exist_ok=True)

    last_payload: TickPayload | None = None
    with (
        path.open("r", encoding="utf-8") as handle,
        Live(console=console, auto_refresh=False) as live,
    ):
        handle.seek(0, 2)
        while True:
            line = handle.readline()
            if not line:
                if last_payload is not None:
                    live.update(render_tick(last_payload), refresh=True)
                    last_payload = None
                time.sleep(poll_interval)
                continue

            record = _parse_record(line)
            if record is None:
                continue
            if record.get("type") != "tick":
                continue
            payload = record.get("payload")
            if payload is None:
                continue
            last_payload = TickPayload.model_validate(payload)


def _parse_record(line: str) -> dict[str, Any] | None:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None
