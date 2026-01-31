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
from latticeville.llm.embedder import Embedder, FakeEmbedder, QwenEmbedder
from latticeville.llm.fake_llm import FakeLLM
from latticeville.llm.mlx_llm import MlxLLM
from latticeville.render.main_viewer import run_main_viewer
from latticeville.sim.tick_loop import run_ticks
from latticeville.sim.world_state import build_tiny_world
from latticeville.sim.world_loader import load_world_config

DEFAULT_LLM_BACKEND = "fake"
DEFAULT_MODEL_ID = "mlx-community/Qwen3-3B-4bit"
DEFAULT_EMBEDDER = "fake"
DEFAULT_EMBED_MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"


def run_simulation(
    base_dir: Path,
    *,
    ticks: int = 10,
    llm_backend: str | None = None,
    model_id: str | None = None,
    embedder_backend: str | None = None,
    embedder_model_id: str | None = None,
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
    embedder = _resolve_embedder(embedder_backend, embedder_model_id)
    memory_log_path = Path("data/memory") / f"{run_dir.name}.jsonl"
    for payload in run_ticks(
        state,
        ticks=ticks,
        policy=policy,
        embedder=embedder,
        memory_log_path=memory_log_path,
    ):
        append_tick_payload(log_path, payload)
    return run_dir


def run_simulation_with_viewer(
    base_dir: Path,
    *,
    ticks: int = 10,
    llm_backend: str | None = None,
    model_id: str | None = None,
    embedder_backend: str | None = None,
    embedder_model_id: str | None = None,
    tick_delay: float = 0.2,
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
    embedder = _resolve_embedder(embedder_backend, embedder_model_id)
    memory_log_path = Path("data/memory") / f"{run_dir.name}.jsonl"
    config = load_world_config()

    def _payloads():
        for payload in run_ticks(
            state,
            ticks=ticks,
            policy=policy,
            embedder=embedder,
            memory_log_path=memory_log_path,
        ):
            append_tick_payload(log_path, payload)
            yield payload

    run_main_viewer(_payloads(), config=config, tick_delay=tick_delay)
    return run_dir


def _resolve_policy(llm_backend: str | None, model_id: str | None) -> LLMPolicy:
    backend = (
        llm_backend or os.getenv("LATTICEVILLE_LLM") or DEFAULT_LLM_BACKEND
    ).lower()
    if backend == "mlx":
        model = model_id or os.getenv("LATTICEVILLE_MODEL_ID") or DEFAULT_MODEL_ID
        return MlxLLM(config=LLMConfig(model_id=model))
    return FakeLLM()


def _resolve_embedder(
    embedder_backend: str | None, embedder_model_id: str | None
) -> Embedder:
    backend = (
        embedder_backend or os.getenv("LATTICEVILLE_EMBEDDER") or DEFAULT_EMBEDDER
    ).lower()
    if backend == "qwen":
        model = (
            embedder_model_id
            or os.getenv("LATTICEVILLE_EMBED_MODEL_ID")
            or DEFAULT_EMBED_MODEL_ID
        )
        return QwenEmbedder(model_id=model)
    return FakeEmbedder()
