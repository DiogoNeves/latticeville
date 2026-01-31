"""Replay logging helpers (JSONL)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from latticeville.sim.contracts import TickPayload

SCHEMA_VERSION = 1
RUN_LOG_NAME = "run.jsonl"


def create_run_folder(
    base_dir: Path, *, timestamp: str | None = None
) -> tuple[Path, Path]:
    run_id = timestamp or _format_timestamp(datetime.now(timezone.utc))
    run_dir = base_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir, run_dir / RUN_LOG_NAME


def write_header(path: Path, metadata: dict[str, Any]) -> None:
    record: dict[str, Any] = {
        "type": "header",
        "schema_version": SCHEMA_VERSION,
        "metadata": metadata,
    }
    _append_record(path, record)


def append_tick_payload(path: Path, payload: TickPayload) -> None:
    record: dict[str, Any] = {
        "type": "tick",
        "schema_version": SCHEMA_VERSION,
        "payload": payload.model_dump(),
    }
    _append_record(path, record)


def _append_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record))
        handle.write("\n")


def _format_timestamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H-%M-%SZ")
