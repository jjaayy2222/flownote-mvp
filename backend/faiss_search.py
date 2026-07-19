# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/faiss_search.py (수정)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - FAISS 검색
"""

import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import numbers
from typing import Any, Dict, List, Optional, Union

import faiss
import numpy as np

from backend.embedding import EmbeddingGenerator
from backend.utils import check_metadata_match


class FAISSRetriever:
    """
    [KO] FAISS 기반 벡터 검색기입니다.
    [EN] FAISS-based vector retriever.
    """

    DEFAULT_FILTER_EXPANSION_FACTOR = 10  # 필터링 시 후보군 확장 기본 배수

    @staticmethod
    def _normalize_expansion_factor(value: Any) -> int:
        """
        [KO] 확장 배수 파라미터의 유효성을 검증하고 정규화(정수 변환)합니다.
        [EN] Validates and normalizes (converts to integer) the expansion factor parameter.

        Args:
            value: [KO] 검증할 확장 배수 값 / [EN] The expansion factor value to validate

        Returns:
            int: [KO] 정규화된 확장 배수 (정수) / [EN] The normalized expansion factor (integer)
        """
        # bool은 numbers.Real의 서브클래스이지만 벡터 검색 배수로는 부적절하므로 차단
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise TypeError(
                f"filter_expansion_factor must be a real number, got {type(value).__name__}"
            )

        if value < 1:
            raise ValueError(f"filter_expansion_factor must be >= 1, got {value}")

        # [KO] 타입 체커 오류(Real 형식이 int로 직접 변환되지 않는 문제)를 방지하고,
        # numpy.float32, Decimal 등 다양한 숫자형 입력을 안전하게 처리하기 위해 float 변환 후 int로 캐스팅합니다.
        # [EN] To prevent type checker errors (Real not directly convertible to int) and safely handle
        # various numeric types like np.float32 or Decimal, we cast to float then int.
        normalized = int(float(value))

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
        [KO] FAISSRetriever 인스턴스를 초기화합니다.
        [EN] Initializes the FAISSRetriever instance.

        Args:
            dimension: [KO] 임베딩 벡터 차원 (기본값: 1536) / [EN] Embedding vector dimension (default: 1536)
            filter_expansion_factor: [KO] 메타데이터 필터링 시 FAISS에서 초기 추출할 후보군 배수 / [EN] Candidate expansion factor for metadata filtering
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
        [KO] 문서와 임베딩 벡터를 FAISS 인덱스에 추가합니다.
        [EN] Adds documents and their embedding vectors to the FAISS index.

        Args:
            embeddings: [KO] 임베딩 벡터 배열 / [EN] Array of embedding vectors
            documents: [KO] 문서 정보 딕셔너리 리스트 (content, metadata 포함) / [EN] List of document info dictionaries (including content, metadata)
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

        # [KO] FAISS 타입 스텁 오류 무시: add()는 np.ndarray를 정상적으로 받지만, mypy 스텁에서는 인자 매칭(x)이 실패하는 문제가 있습니다.
        # [EN] Ignore FAISS type stub error: add() accepts np.ndarray correctly at runtime, but mypy stub fails on argument matching (x).
        self.index.add(embeddings_np)  # type: ignore[call-arg]

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
        [KO] 주어진 쿼리와 가장 유사한 문서를 검색합니다.
        [EN] Searches for documents most similar to the given query.

        Args:
            query: [KO] 검색 쿼리 문자열 / [EN] The search query string
            k: [KO] 반환할 최대 결과 수 / [EN] Maximum number of results to return
            metadata_filter: [KO] 메타데이터 필터 조건 딕셔너리 (예: {"category": "Projects"}) / [EN] Metadata filter condition dictionary
            filter_expansion_factor: [KO] 이 검색에만 일시적으로 적용할 후보군 확장 배수 (None이면 인스턴스 값 사용) / [EN] Temporary candidate expansion factor to apply (uses instance value if None)

        Returns:
            List[Dict]: [KO] 검색 결과 리스트 (content, metadata, score, distance 포함) / [EN] List of search results (including content, metadata, score, distance)
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
        # [KO] FAISS 타입 스텁 오류 무시: search()는 정상 동작하지만, mypy 스텁에서 필요한 인자(k, distances 등)가 누락되었다고 잘못 경고하는 문제가 있습니다.
        # [EN] Ignore FAISS type stub error: search() works correctly at runtime, but mypy stub incorrectly warns about missing arguments (k, distances, etc).
        distances, indices = self.index.search(query_vector, search_k)  # type: ignore[call-arg]

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
        """
        [KO] FAISS 인덱스와 저장된 문서를 모두 초기화합니다.
        [EN] Clears the FAISS index and all stored documents.
        """
        self.index = faiss.IndexFlatL2(self.dimension)
        self.documents = []

    def size(self) -> int:
        """
        [KO] 인덱스에 저장된 문서의 총 개수를 반환합니다.
        [EN] Returns the total number of documents stored in the index.

        Returns:
            int: [KO] 저장된 문서 수 / [EN] The number of stored documents
        """
        return self.index.ntotal

    def save(self, directory: Union[str, Path]) -> None:
        """
        [KO] 인덱스와 메타데이터를 지정된 디렉토리에 저장합니다.
        [EN] Saves the index and metadata to the specified directory.

        Args:
            directory: [KO] 저장할 디렉토리 경로 / [EN] The directory path to save to
        """
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)

        # FAISS 인덱스 저장
        faiss.write_index(self.index, str(directory / "faiss.index"))

        # 문서 메타데이터 저장
        with open(directory / "documents.json", "w", encoding="utf-8") as f:
            json.dump(self.documents, f, ensure_ascii=False, indent=2)

        logger.info("FAISS 인덱스 및 메타데이터 저장 완료: %s", directory)

    def load(self, directory: Union[str, Path]) -> None:
        """
        [KO] 지정된 디렉토리에서 인덱스와 메타데이터를 로드합니다.
        [EN] Loads the index and metadata from the specified directory.

        Args:
            directory: [KO] 로드할 파일이 있는 디렉토리 경로 / [EN] The directory path to load from
        """
        directory = Path(directory)
        index_path = directory / "faiss.index"
        docs_path = directory / "documents.json"

        if not index_path.exists() or not docs_path.exists():
            raise FileNotFoundError(f"FAISS index files not found in {directory}")

        # FAISS 인덱스 로드
        self.index = faiss.read_index(str(index_path))

        # 문서 메타데이터 로드
        with open(docs_path, "r", encoding="utf-8") as f:
            self.documents = json.load(f)

        # 차원 검증 (불일치 시 경고만 남기고, self.dimension(명시적 설정값)은 유지)
        if self.index.d != self.dimension:
            logger.warning(
                "Loaded index dimension (%d) differs from configured dimension (%d). "
                "Keeping configured dimension. Ensure the saved index matches your embedding model.",
                self.index.d,
                self.dimension,
            )

        logger.info(
            "FAISS 인덱스 및 메타데이터 로드 완료: %d개 문서", len(self.documents)
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
    texts = []
    for doc in docs:
        content = doc.get("content")
        if not isinstance(content, str):
            raise TypeError(
                f"Document content must be a string, got {type(content).__name__}"
            )
        texts.append(content)

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
