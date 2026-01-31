from latticeville.llm.embedder import FakeEmbedder
from latticeville.sim.memory import MemoryStream


def test_retrieval_ranks_by_importance_when_other_scores_equal() -> None:
    stream = MemoryStream(embedder=FakeEmbedder())
    stream.append(
        description="Routine note",
        created_at=1,
        importance=1.0,
        type="observation",
    )
    stream.append(
        description="Important note",
        created_at=1,
        importance=5.0,
        type="observation",
    )

    results = stream.retrieve(query="note", current_tick=2, k=2)
    assert results[0].record.description == "Important note"


def test_retrieval_stable_when_scores_equal() -> None:
    stream = MemoryStream(embedder=FakeEmbedder())
    first = stream.append(
        description="Same note",
        created_at=1,
        importance=1.0,
        type="observation",
    )
    second = stream.append(
        description="Same note",
        created_at=1,
        importance=1.0,
        type="observation",
    )

    results = stream.retrieve(query="Same note", current_tick=2, k=2)
    assert results[0].record.record_id == first.record_id
    assert results[1].record.record_id == second.record_id
