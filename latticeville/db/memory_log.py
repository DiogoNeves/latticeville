"""Append-only memory logging (JSONL)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from latticeville.sim.memory import MemoryRecord


def append_memory_record(path: Path, *, agent_id: str, record: MemoryRecord) -> None:
    payload: dict[str, Any] = {
        "agent_id": agent_id,
        "record": record.to_dict(),
    }
    _append_record(path, payload)


def _append_record(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload))
        handle.write("\n")
