"""Memory stream and retrieval scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import exp, sqrt
from typing import Iterable
from uuid import uuid4

from latticeville.llm.embedder import Embedder


@dataclass
class MemoryRecord:
    description: str
    created_at: int
    last_accessed_at: int
    importance: float
    type: str
    links: list[str] = field(default_factory=list)
    embedding: list[float] = field(default_factory=list)
    record_id: str = field(default_factory=lambda: uuid4().hex)

    def to_dict(self) -> dict:
        return {
            "id": self.record_id,
            "description": self.description,
            "created_at": self.created_at,
            "last_accessed_at": self.last_accessed_at,
            "importance": self.importance,
            "type": self.type,
            "links": list(self.links),
        }


@dataclass
class RetrievalResult:
    record: MemoryRecord
    score: float


class MemoryStream:
    def __init__(
        self,
        *,
        embedder: Embedder,
        recency_decay: float = 0.01,
    ) -> None:
        self._records: list[MemoryRecord] = []
        self._embedder = embedder
        self._recency_decay = recency_decay

    @property
    def records(self) -> list[MemoryRecord]:
        return list(self._records)

    def append(
        self,
        *,
        description: str,
        created_at: int,
        importance: float,
        type: str,
        links: list[str] | None = None,
    ) -> MemoryRecord:
        embedding = self._embedder.embed(description)
        record = MemoryRecord(
            description=description,
            created_at=created_at,
            last_accessed_at=created_at,
            importance=importance,
            type=type,
            links=links or [],
            embedding=embedding,
        )
        self._records.append(record)
        return record

    def retrieve(
        self,
        *,
        query: str,
        current_tick: int,
        k: int = 3,
    ) -> list[RetrievalResult]:
        if not self._records:
            return []

        query_embedding = self._embedder.embed(query)
        recency_raw = [
            exp(-self._recency_decay * (current_tick - record.last_accessed_at))
            for record in self._records
        ]
        relevance_raw = [
            _cosine_similarity(query_embedding, record.embedding)
            for record in self._records
        ]
        importance_raw = [record.importance for record in self._records]

        recency_norm = _minmax_norm(recency_raw)
        relevance_norm = _minmax_norm(relevance_raw)
        importance_norm = _minmax_norm(importance_raw)

        scored: list[RetrievalResult] = []
        for index, record in enumerate(self._records):
            score = recency_norm[index] + relevance_norm[index] + importance_norm[index]
            scored.append(RetrievalResult(record=record, score=score))

        ranked = sorted(
            enumerate(scored),
            key=lambda item: (-item[1].score, item[0]),
        )
        results = [item[1] for item in ranked[:k]]
        for result in results:
            result.record.last_accessed_at = current_tick
        return results


def _minmax_norm(values: Iterable[float]) -> list[float]:
    values_list = list(values)
    if not values_list:
        return []
    min_val = min(values_list)
    max_val = max(values_list)
    if max_val == min_val:
        return [0.0 for _ in values_list]
    return [(value - min_val) / (max_val - min_val) for value in values_list]


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b:
        return 0.0
    length = min(len(vec_a), len(vec_b))
    dot = sum(vec_a[i] * vec_b[i] for i in range(length))
    norm_a = sqrt(sum(vec_a[i] * vec_a[i] for i in range(length)))
    norm_b = sqrt(sum(vec_b[i] * vec_b[i] for i in range(length)))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
