"""Persistent FAISS document embedding behavior."""

from pathlib import Path

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
