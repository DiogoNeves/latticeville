"""Embedding helpers for retrieval."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

import torch
from transformers import AutoModel, AutoTokenizer


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]:
        """Return an embedding vector for the input text."""


@dataclass
class FakeEmbedder(Embedder):
    dim: int = 8

    def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = []
        for index in range(self.dim):
            byte = digest[index % len(digest)]
            values.append((byte / 255.0) * 2.0 - 1.0)
        return values


@dataclass
class QwenEmbedder(Embedder):
    model_id: str
    device: str | None = None

    def __post_init__(self) -> None:
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_id)
        self._model = AutoModel.from_pretrained(self.model_id)
        resolved = self.device or (
            "mps" if torch.backends.mps.is_available() else "cpu"
        )
        self._device = torch.device(resolved)
        self._model.to(self._device)
        self._model.eval()

    def embed(self, text: str) -> list[float]:
        encoded = self._tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=512,
        )
        encoded = {key: value.to(self._device) for key, value in encoded.items()}
        with torch.no_grad():
            outputs = self._model(**encoded)
        last_hidden = outputs.last_hidden_state
        attention = encoded.get("attention_mask")
        if attention is None:
            pooled = last_hidden.mean(dim=1)
        else:
            mask = attention.unsqueeze(-1)
            masked = last_hidden * mask
            pooled = masked.sum(dim=1) / mask.sum(dim=1).clamp(min=1)
        vector = pooled[0].detach().cpu().tolist()
        return [float(value) for value in vector]
