"""Replay logging helpers (JSONL)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from latticeville.sim.contracts import TickPayload

SCHEMA_VERSION = 1


def append_tick_payload(path: Path, payload: TickPayload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "payload": payload.model_dump(),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record))
        handle.write("\n")
