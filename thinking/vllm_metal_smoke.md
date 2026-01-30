# vLLM Metal: Direct offline API

This document captures how to run LLM generation and embeddings **directly** (no HTTP server) on Apple Silicon. Both work offline and are the recommended approach for Latticeville.

## Key findings

### vllm-mlx architecture

- **vllm-mlx** is optimized for Apple Silicon Metal GPU but is **server-oriented**.
- It exposes an OpenAI-compatible HTTP API (`/v1/chat/completions`, `/v1/embeddings`).
- It does **not** provide a direct Python API like standard vLLM's `LLM` class.
- It does **not** support embedding models natively (attempts fail with model type mismatches).

### Direct offline APIs (recommended)

**Both APIs work directly in Python - no HTTP server needed.**

For **LLM generation** (Metal GPU):
- Use `mlx-lm` directly (comes with `vllm-mlx` package).
- API: `from mlx_lm import load, generate`
- Example:
  ```python
  model, tokenizer = load("mlx-community/Qwen3-0.6B-8bit")
  generation = generate(model, tokenizer, prompt="...", max_tokens=256)
  ```
- Works offline, in-process, Metal GPU accelerated.

For **embeddings** (CPU):
- Use standard `vllm` with `runner="pooling"`.
- API: `from vllm import LLM`
- Note: API changed from `task="embed"` (older docs) to `runner="pooling"` (v0.14+).
- Example:
  ```python
  os.environ["VLLM_PLUGINS"] = ""  # Disable MLX plugin
  llm = LLM(model="BAAI/bge-small-en-v1.5", runner="pooling", enforce_eager=True)
  outputs = llm.embed([prompt])
  embeds = outputs[0].outputs.embedding
  ```
- Works offline, in-process, CPU-based.

### Compatibility notes

- Standard vLLM **cannot** load MLX quantized models directly (tensor shape mismatches).
- Standard vLLM **can** detect vllm-mlx as a plugin, but there are compatibility issues when trying to use MLX models.
- Disable MLX plugin for embeddings: `os.environ["VLLM_PLUGINS"] = ""` before importing vLLM.

## Setup

```bash
# Create venv
python -m venv .venv

# Install both packages
.venv/bin/python -m pip install vllm-mlx vllm
```

Why both:
- `vllm-mlx`: Provides `mlx-lm` for Metal-accelerated LLM generation.
- `vllm`: Provides offline pooling API for embeddings.

## Model compatibility

**LLM models (mlx-lm):**
- Works with MLX quantized models from `mlx-community/` (e.g., `Qwen3-0.6B-8bit`).
- Models are downloaded from HuggingFace automatically.

**Embedding models (vLLM pooling):**
- Works with standard HuggingFace embedding models (e.g., `BAAI/bge-small-en-v1.5`).
- Must be compatible with sentence-transformers format.
- Models are downloaded from HuggingFace automatically.

## Architecture decision

**For Latticeville, use direct offline APIs:**
- **LLM**: `mlx-lm` direct API (Metal GPU, offline, in-process).
- **Embeddings**: Standard vLLM pooling API (CPU, offline, in-process).

**Benefits:**
- No HTTP server process to manage.
- Everything runs in-process with the simulation.
- Metal GPU acceleration for LLM generation.
- Simple Python API, similar to standard vLLM docs.
