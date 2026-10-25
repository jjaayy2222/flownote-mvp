"""Persistent FAISS document embedding behavior."""

from pathlib import Path

import pytest

from backend.faiss_search import FAISSRetriever


def test_persistent_retriever_restores_and_upserts_by_document_id(
    tmp_path: Path,
) -> None:
    first = FAISSRetriever(dimension=3, persist_directory=tmp_path)
    first.upsert_document(
        document_id="note-a",
        embedding=[1.0, 0.0, 0.0],
        content="first version",
        metadata={"user_id_hash": "user-a"},
    )
    first.upsert_document(
        document_id="note-b",
        embedding=[0.0, 1.0, 0.0],
        content="second note",
        metadata={"user_id_hash": "user-b"},
    )

    restored = FAISSRetriever(
        dimension=3, persist_directory=tmp_path, load_on_init=True
    )

    assert restored.size() == 2
    assert restored.get_embeddings(["note-a"], {"user_id_hash": "user-a"}) == {
        "note-a": [1.0, 0.0, 0.0]
    }
    assert restored.get_embeddings(["note-a"], {"user_id_hash": "user-b"}) == {}

    restored.upsert_document(
        document_id="note-a",
        embedding=[0.0, 0.0, 1.0],
        content="updated version",
        metadata={"user_id_hash": "user-a"},
    )

    latest = FAISSRetriever(dimension=3, persist_directory=tmp_path, load_on_init=True)
    assert latest.size() == 2
    assert latest.documents[0]["content"] == "second note"
    assert latest.get_embeddings(["note-a"]) == {"note-a": [0.0, 0.0, 1.0]}


def test_scoped_search_expands_until_it_finds_matching_documents() -> None:
    retriever = FAISSRetriever(dimension=2)
    retriever.embedding_generator.generate_embeddings = lambda texts: {
        "embeddings": [[1.0, 0.0]],
        "tokens": 1,
        "cost": 0.0,
    }
    for index in range(20):
        retriever.add_documents(
            [[1.0, index / 1000]],
            [{"content": "other tenant", "metadata": {"user_id_hash": "other"}}],
        )
    retriever.add_documents(
        [[0.0, 1.0]],
        [{"content": "matching tenant", "metadata": {"user_id_hash": "target"}}],
    )

    results = retriever.search("query", k=1, metadata_filter={"user_id_hash": "target"})

    assert [item["content"] for item in results] == ["matching tenant"]


def test_search_returns_metadata_copy() -> None:
    retriever = FAISSRetriever(dimension=2)
    retriever.embedding_generator.generate_embeddings = lambda texts: {
        "embeddings": [[1.0, 0.0]],
        "tokens": 1,
        "cost": 0.0,
    }
    retriever.upsert_document("note", [1.0, 0.0], "content", {"user_id_hash": "owner"})

    result = retriever.search("query", metadata_filter={"user_id_hash": "owner"})
    result[0]["metadata"].pop("user_id_hash")

    assert retriever.documents[0]["metadata"]["user_id_hash"] == "owner"


def test_scoped_delete_removes_only_matching_documents() -> None:
    retriever = FAISSRetriever(dimension=2)
    for document_id, owner in (("a", "owner-a"), ("b", "owner-b")):
        retriever.upsert_document(
            document_id, [1.0, 0.0], document_id, {"user_id_hash": owner}
        )

    assert retriever.delete_documents({"user_id_hash": "owner-a"}) == 1
    assert retriever.size() == 1
    assert retriever.documents[0]["document_id"] == "b"


def test_load_rejects_persisted_dimension_mismatch(tmp_path: Path) -> None:
    FAISSRetriever(dimension=2, persist_directory=tmp_path).upsert_document(
        "note", [1.0, 0.0], "content"
    )
    retriever = FAISSRetriever(dimension=3)

    with pytest.raises(ValueError, match="dimension does not match"):
        retriever.load(tmp_path)
