import sys
import os
from pathlib import Path
import pytest
import numpy as np
from unittest.mock import patch

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.faiss_search import FAISSRetriever
from backend.utils import check_metadata_match


def test_unhashable_metadata():
    print("\n[V1] Checking unhashable metadata...")
    doc_metadata = {
        "tags": [{"name": "AI"}, {"name": "NLP"}]
    }  # 리스트 내 dict (unhashable)

    # 1. 일치하는 경우
    filter1 = {"tags": [{"name": "AI"}]}
    assert check_metadata_match(doc_metadata, filter1) == True

    # 2. 일치하지 않는 경우
    filter2 = {"tags": [{"name": "Search"}]}
    assert check_metadata_match(doc_metadata, filter2) == False
    print("✅ Unhashable metadata check passed!")


def test_expansion_factor_types():
    print("\n[V2] Checking expansion factor types...")
    # 1. Valid float (e.g., 2.5 -> 2)
    retriever = FAISSRetriever(filter_expansion_factor=2.5)
    assert retriever.filter_expansion_factor == 2

    # 2. Invalid types (bool)
    with pytest.raises(TypeError, match="must be a real number"):
        FAISSRetriever(filter_expansion_factor=True)

    # 3. Invalid types (str)
    with pytest.raises(TypeError, match="must be a real number"):
        FAISSRetriever(filter_expansion_factor="10")

    # 4. Range check (0.5 -> caught by value < 1 check)
    with pytest.raises(ValueError, match="must be >= 1"):
        FAISSRetriever(filter_expansion_factor=0.5)

    print("✅ Expansion factor type check passed!")


def test_expansion_factor_conditional_validation():
    print("\n[V3] Checking conditional validation in search...")
    with patch("backend.embedding.EmbeddingGenerator.generate_embeddings") as mock_gen:
        mock_gen.return_value = {"embeddings": [[0.1] * 1536]}
        retriever = FAISSRetriever()

        # 1. metadata_filter가 없으면 잘못된 값을 넘겨도 무시됨 (리뷰어 요청 사항)
        retriever.documents = [{"content": "v3-test"}]
        retriever.index.add(np.array([[0.1] * 1536], dtype=np.float32))

        try:
            # metadata_filter=None이면 expansion=0을 무시해야 함
            retriever.search("query", metadata_filter=None, filter_expansion_factor=0)
            print("✅ Conditional validation (None filter) passed!")
        except (ValueError, TypeError):
            # If it raises, it's failing the conditional logic
            import traceback

            traceback.print_exc()
            pytest.fail("Should not have raised Error when metadata_filter is None")

        # 2. metadata_filter가 있으면 검증 수행
        with pytest.raises(ValueError, match="must be >= 1"):
            retriever.search(
                "query", metadata_filter={"id": 1}, filter_expansion_factor=0
            )
        print("✅ Conditional validation (With filter) passed!")


if __name__ == "__main__":
    test_unhashable_metadata()
    test_expansion_factor_types()
    test_expansion_factor_conditional_validation()
    print("\nALL REVIEWS ADDRESSED SUCCESSFULLY!")
