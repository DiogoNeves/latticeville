"""Read replay logs and yield TickPayloads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from latticeville.sim.contracts import TickPayload


def read_tick_payloads(path: Path) -> Iterator[TickPayload]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = _parse_record(line)
            if not record:
                continue
            if record.get("type") != "tick":
                continue
            payload = record.get("payload")
            if payload is None:
                continue
            yield TickPayload.model_validate(payload)


def _parse_record(line: str) -> dict | None:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None
