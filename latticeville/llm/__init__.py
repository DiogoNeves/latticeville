"""Local LLM adapters and interfaces."""

from latticeville.llm.base import LLMConfig, LLMPolicy, build_valid_targets
from latticeville.llm.embedder import FakeEmbedder, QwenEmbedder
from latticeville.llm.fake_llm import FakeLLM
from latticeville.llm.mlx_llm import MlxLLM
from latticeville.llm.prompt_fixtures import fixture_for
from latticeville.llm.prompts import PromptId, parse_prompt_output, render_prompt

__all__ = [
    "LLMConfig",
    "LLMPolicy",
    "FakeLLM",
    "MlxLLM",
    "FakeEmbedder",
    "QwenEmbedder",
    "build_valid_targets",
    "PromptId",
    "render_prompt",
    "parse_prompt_output",
    "fixture_for",
]
