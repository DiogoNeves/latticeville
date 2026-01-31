from latticeville.llm.embedder import FakeEmbedder


def test_fake_embedder_deterministic() -> None:
    embedder = FakeEmbedder(dim=8)
    first = embedder.embed("hello")
    second = embedder.embed("hello")
    assert first == second


def test_fake_embedder_changes_with_input() -> None:
    embedder = FakeEmbedder(dim=8)
    first = embedder.embed("hello")
    second = embedder.embed("world")
    assert first != second
