# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/faiss_search.py (수정)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - FAISS 검색
"""

import sys
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import faiss
import numpy as np
import numbers
from typing import List, Dict, Union, Optional, Any
from backend.embedding import EmbeddingGenerator
from backend.utils import check_metadata_match


class FAISSRetriever:
    """FAISS 기반 벡터 검색"""

    DEFAULT_FILTER_EXPANSION_FACTOR = 10  # 필터링 시 후보군 확장 기본 배수

    @staticmethod
    def _normalize_expansion_factor(value: Any) -> int:
        """확장 배수 파라미터 유효성 검증 및 정규화 (정수 변환)"""
        # bool은 numbers.Real의 서브클래스이지만 벡터 검색 배수로는 부적절하므로 차단
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise TypeError(
                f"filter_expansion_factor must be a real number, got {type(value).__name__}"
            )

        if value < 1:
            raise ValueError(f"filter_expansion_factor must be >= 1, got {value}")

        normalized = int(value)

        if normalized < 1:
            # 0.5와 같이 (0.0, 1.0) 사이의 값이 들어온 경우 정수 변환 시 0이 됨
            raise ValueError(
                f"filter_expansion_factor must be >= 1 after normalization, got {normalized}"
            )

        return normalized

    def __init__(
        self,
        dimension: int = 1536,
        filter_expansion_factor: int = DEFAULT_FILTER_EXPANSION_FACTOR,
    ):
        """
        Args:
            dimension: 임베딩 벡터 차원 (text-embedding-3-small: 1536)
            filter_expansion_factor: 메타데이터 필터링 시 FAISS에서 초기 추출할 후보군 배수
        """
        self.dimension = dimension
        self.index = faiss.IndexFlatL2(dimension)
        self.documents = []  # dict 객체 저장
        self.embedding_generator = EmbeddingGenerator()
        self.filter_expansion_factor = self._normalize_expansion_factor(
            filter_expansion_factor
        )

    def add_documents(
        self,
        embeddings: np.ndarray,  # 순서 변경
        documents: List[Dict],  # Dict 타입으로 변경
    ):
        """
        문서와 임베딩 추가

        Args:
            embeddings: 임베딩 벡터 배열
            documents: 문서 dict 리스트 (content, metadata 포함)
        """
        if not documents or embeddings is None:
            return

        if len(documents) != len(embeddings):
            raise ValueError(
                f"문서 수({len(documents)})와 임베딩 수({len(embeddings)})가 일치하지 않습니다!"
            )

        # NumPy 배열로 변환
        if not isinstance(embeddings, np.ndarray):
            embeddings_np = np.array(embeddings, dtype=np.float32)
        else:
            embeddings_np = embeddings.astype(np.float32)

        # FAISS 인덱스에 추가
        self.index.add(embeddings_np)

        # 문서 dict 그대로 저장
        self.documents.extend(documents)
        print(f"✅ FAISS에 {len(documents)}개 문서 추가 완료")

    def search(
        self,
        query: str,
        k: int = 3,
        metadata_filter: Optional[Dict] = None,
        filter_expansion_factor: Optional[int] = None,
    ) -> List[Dict]:
        """
        쿼리에 가장 유사한 문서 검색

        Args:
            query: 검색 쿼리
            k: 반환할 결과 수
            metadata_filter: 메타데이터 필터 조건 (예: {"category": "Projects"})
            filter_expansion_factor: 이 검색에만 일시적으로 적용할 후보군 확장 배수 (None이면 인스턴스 값 사용)

        Returns:
            검색 결과 리스트 (content, metadata, score 포함)
        """
        # 1. 파라미터 유효성 검증 (메타데이터 필터링이 활성화된 경우에만 후보군 확장 배수 적용)
        if metadata_filter is not None:
            target_factor = (
                self.filter_expansion_factor
                if filter_expansion_factor is None
                else filter_expansion_factor
            )
            expansion = self._normalize_expansion_factor(target_factor)
        else:
            # 필터링을 사용하지 않는 경우 확장이 필요 없으므로 1로 고정
            expansion = 1

        if self.index.ntotal == 0:
            return []

        # 쿼리 임베딩 생성
        result = self.embedding_generator.generate_embeddings([query])
        query_embedding = result["embeddings"][0]

        # NumPy 배열로 변환
        query_vector = np.array([query_embedding], dtype=np.float32)

        search_k = min(self.index.ntotal, k * expansion if metadata_filter else k)
        distances, indices = self.index.search(query_vector, search_k)

        # 결과 반환 및 필터링
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(self.documents):
                continue

            doc = self.documents[idx]

            # 메타데이터 필터 체크
            if metadata_filter and not check_metadata_match(
                doc.get("metadata", {}), metadata_filter
            ):
                continue

            # 유사도 계산
            similarity = 1 / (1 + float(dist))

            results.append(
                {
                    "content": doc.get("content", ""),
                    "metadata": doc.get("metadata", {}),
                    "score": similarity,
                    "distance": float(dist),
                }
            )

            # k개 채워지면 중단
            if len(results) >= k:
                break

        return results

    def clear(self):
        """인덱스 초기화"""
        self.index = faiss.IndexFlatL2(self.dimension)
        self.documents = []

    def size(self) -> int:
        """인덱스에 저장된 문서 수"""
        return self.index.ntotal

    def save(self, directory: Union[str, Path]):
        """인덱스와 메타데이터를 디스크에 저장"""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)

        # FAISS 인덱스 저장
        faiss.write_index(self.index, str(directory / "faiss.index"))

        # 문서 메타데이터 저장
        import json

        with open(directory / "documents.json", "w", encoding="utf-8") as f:
            json.dump(self.documents, f, ensure_ascii=False, indent=2)

        logger.info(f"✅ FAISS 인덱스 및 메타데이터 저장 완료: {directory}")

    def load(self, directory: Union[str, Path]):
        """디스크에서 인덱스와 메타데이터 로드"""
        directory = Path(directory)
        index_path = directory / "faiss.index"
        docs_path = directory / "documents.json"

        if not index_path.exists() or not docs_path.exists():
            raise FileNotFoundError(f"FAISS index files not found in {directory}")

        # FAISS 인덱스 로드
        self.index = faiss.read_index(str(index_path))

        # 문서 메타데이터 로드
        import json

        with open(docs_path, "r", encoding="utf-8") as f:
            self.documents = json.load(f)

        # 차원 검증
        if self.index.d != self.dimension:
            logger.warning(
                f"Loaded index dimension ({self.index.d}) differs from self.dimension ({self.dimension})"
            )
            self.dimension = self.index.d

        logger.info(
            f"✅ FAISS 인덱스 및 메타데이터 로드 완료: {len(self.documents)}개 문서"
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 테스트 코드 (수정 버전)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    print("=" * 50)
    print("FAISS 검색 테스트")
    print("=" * 50)

    # 1. Retriever 초기화
    retriever = FAISSRetriever()

    # 2. 테스트 문서 (dict 구조)
    docs = [
        {
            "content": "FlowNote는 AI 대화 관리 도구입니다.",
            "metadata": {"source": "test.txt", "chunk_index": 0},
        },
        {
            "content": "대화 내용을 검색하고 분석할 수 있습니다.",
            "metadata": {"source": "test.txt", "chunk_index": 1},
        },
        {
            "content": "마크다운으로 대화를 내보낼 수 있습니다.",
            "metadata": {"source": "test.txt", "chunk_index": 2},
        },
    ]

    # 3. 임베딩 생성
    embedding_generator = EmbeddingGenerator()
    texts = [doc["content"] for doc in docs]

    # ✅ 수정: result에서 embeddings 추출!
    result = embedding_generator.generate_embeddings(texts)
    embeddings = result["embeddings"]  # 추가

    print(f"\n✅ 임베딩 생성 완료:")
    print(f" - 청크 수: {len(embeddings)}")
    print(f" - 토큰 수: {result['tokens']}")
    print(f" - 예상 비용: ${result['cost']:.6f}")
    print(f" - 벡터 차원: {len(embeddings[0])}")

    # 4. NumPy 배열로 변환 (FAISS가 기대하는 형태)
    embeddings_np = np.array(embeddings, dtype=np.float32)

    # 5. 문서 추가
    retriever.add_documents(embeddings_np, docs)
    print(f"\n✅ FAISS 인덱스 추가 완료")
    print(f"    - 총 문서 수: {len(docs)}")
    print(f"    - 인덱스 크기: {retriever.size()}")

    # 6. 검색
    query = "대화를 어떻게 관리하나요?"
    print(f"\n🔍 검색 쿼리: '{query}'")
    results = retriever.search(query, k=2)

    print(f"\n검색 결과 ({len(results)}개):")
    print("-" * 50)
    for i, result in enumerate(results, 1):
        print(f"\n{i}위:")
        print(f"    - 유사도: {result['score']:.4f}")
        print(f"    - 내용: {result['content']}")
        print(f"    - 출처: {result['metadata']['source']}")

    print("\n" + "=" * 50)


"""result_3

    ==================================================
    FAISS 검색 테스트
    ==================================================

    ✅ 문서 추가 완료!
        - 총 문서 수: 3
        - 인덱스 크기: 3

    검색 결과:

    1위:
        - 유사도: 0.5385
        - 텍스트: 대화 내용을 검색하고 분석할 수 있습니다.

    2위:
        - 유사도: 0.4233
        - 텍스트: 마크다운으로 대화를 내보낼 수 있습니다.

    ==================================================

"""


"""result_4

    ==================================================
    FAISS 검색 테스트
    ==================================================

    ✅ 임베딩 생성 완료:
        - 청크 수: 3
        - 토큰 수: 48
        - 예상 비용: $0.000001
        - 벡터 차원: 1536
    ✅ FAISS에 3개 문서 추가 완료

    ✅ FAISS 인덱스 추가 완료
        - 총 문서 수: 3
        - 인덱스 크기: 3

    🔍 검색 쿼리: '대화를 어떻게 관리하나요?'

    검색 결과 (2개):
    --------------------------------------------------

    1위:
        - 유사도: 1.0000
        - 내용: FlowNote는 AI 대화 관리 도구입니다.
        - 출처: test.txt

    2위:
        - 유사도: 0.4368
        - 내용: 마크다운으로 대화를 내보낼 수 있습니다.
        - 출처: test.txt

    ==================================================

"""

"""result_5

    ==================================================
    FAISS 검색 테스트
    ==================================================

    ✅ 임베딩 생성 완료:
        - 청크 수: 3
        - 토큰 수: 48
        - 예상 비용: $0.000001
        - 벡터 차원: 1536
    ✅ FAISS에 3개 문서 추가 완료

    ✅ FAISS 인덱스 추가 완료
        - 총 문서 수: 3
        - 인덱스 크기: 3

    🔍 검색 쿼리: '대화를 어떻게 관리하나요?'

    검색 결과 (2개):
    --------------------------------------------------

    1위:
        - 유사도: 0.5387
        - 내용: 대화 내용을 검색하고 분석할 수 있습니다.
        - 출처: test.txt

    2위:
        - 유사도: 0.4233
        - 내용: 마크다운으로 대화를 내보낼 수 있습니다.
        - 출처: test.txt

    ==================================================

"""
