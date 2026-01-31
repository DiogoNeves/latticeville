"""Application entry for running the simulation loop."""

from __future__ import annotations

import os
from pathlib import Path

from latticeville.db.replay_log import (
    append_tick_payload,
    create_run_folder,
    write_header,
)
from latticeville.llm.base import LLMConfig, LLMPolicy
from latticeville.llm.fake_llm import FakeLLM
from latticeville.llm.mlx_llm import MlxLLM
from latticeville.sim.tick_loop import run_ticks
from latticeville.sim.world_state import build_tiny_world

DEFAULT_LLM_BACKEND = "fake"
DEFAULT_MODEL_ID = "mlx-community/Qwen3-3B-4bit"


def run_simulation(
    base_dir: Path,
    *,
    ticks: int = 10,
    llm_backend: str | None = None,
    model_id: str | None = None,
) -> Path:
    run_dir, log_path = create_run_folder(base_dir)
    write_header(
        log_path,
        metadata={
            "run_id": run_dir.name,
            "created_at": run_dir.name,
            "ticks": ticks,
        },
    )
    state = build_tiny_world()
    policy = _resolve_policy(llm_backend, model_id)
    for payload in run_ticks(state, ticks=ticks, policy=policy):
        append_tick_payload(log_path, payload)
    return run_dir


def _resolve_policy(llm_backend: str | None, model_id: str | None) -> LLMPolicy:
    backend = (
        llm_backend or os.getenv("LATTICEVILLE_LLM") or DEFAULT_LLM_BACKEND
    ).lower()
    if backend == "mlx":
        model = model_id or os.getenv("LATTICEVILLE_MODEL_ID") or DEFAULT_MODEL_ID
        return MlxLLM(config=LLMConfig(model_id=model))
    return FakeLLM()
