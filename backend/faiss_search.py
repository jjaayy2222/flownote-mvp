# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/faiss_search.py (수정)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - FAISS 검색
"""

import json
import logging
import sys
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import functools
import numbers
from collections import abc
from typing import Any, Dict, List, Optional, Tuple, Union

import faiss
import numpy as np

from backend.config import ModelConfig
from backend.embedding import EmbeddingGenerator
from backend.utils import check_metadata_match


@functools.lru_cache(maxsize=None)
def _get_array_like_types() -> Tuple[type, ...]:
    """[KO] numpy.ndarray 및 pandas DataFrame/Series 타입을 포함하는 완전한 투플을 첫 호출 시 1회만 생성하고 이후 재사용합니다.
    [EN] Lazily builds and caches a full tuple of array-like types (numpy.ndarray + pandas types) on first call.
         Reusing this cached tuple avoids per-call tuple allocation in _validate_content.
    """
    pandas_types: Tuple[type, ...] = ()
    try:
        import pandas as _pd  # noqa: PLC0415

        pandas_types = (_pd.DataFrame, _pd.Series)
    except ImportError:  # sourcery skip: use-contextlib-suppress
        pass  # pandas 미설치 환경 / pandas not installed
    return (np.ndarray, *pandas_types)


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

        # [KO] numpy.float32 등 다양한 숫자형의 안전한 int 캐스팅을 위해 float를 거침 (타입 체커 오류 방지)
        # [EN] Cast via float to safely handle numeric types like np.float32 and prevent type errors.
        normalized = int(float(value))

        if normalized < 1:
            # 0.5와 같이 (0.0, 1.0) 사이의 값이 들어온 경우 정수 변환 시 0이 됨
            raise ValueError(
                f"filter_expansion_factor must be >= 1 after normalization, got {normalized}"
            )

        return normalized

    def _validate_content(self, content: Any) -> str:
        """
        [KO] 문서 내용이 스칼라(문자열 등)인지 검증 및 변환하는 헬퍼 메서드입니다.
        [EN] Helper method to validate and convert document content to a string.
        """
        if isinstance(content, str):
            return content
        if content is None:
            raise TypeError("Document content cannot be None.")
        # [KO] 전형적인 컨테이너 타입(abc.Collection의 서브클래스인 Mapping, Sequence, Set 등을 모두 포함) 및
        #      NumPy/Pandas의 배열형 객체(ndarray, DataFrame, Series)는 임베딩 대상이 아니므로 명시적으로 차단합니다.
        #      단, str/bytes/bytearray와 같은 스칼라형 값과, 단순히 __iter__만 구현한 커스텀 타입은 차단 대상이 아닙니다.
        # [EN] Block container types (abc.Collection covers Mapping, Sequence, Set and their subclasses) and
        #      NumPy/Pandas array-like objects (ndarray, DataFrame, Series) as they are not embeddable.
        #      Scalar text types (str/bytes/bytearray) and custom types that merely implement __iter__ remain allowed.
        scalar_like = isinstance(content, (str, bytes, bytearray))
        # abc.Collection은 Mapping/Sequence/Set을 모두 포함하므로 하나로 충분합니다.
        # abc.Collection covers abc.Mapping, abc.Sequence, and abc.Set as subclasses.
        container_like = isinstance(content, abc.Collection) and not scalar_like
        # [KO] numpy.ndarray 및 pandas 배열형 타입은 _get_array_like_types()를 통해 첫 호출 시 1회만 투플을 생성하고 이후 재사용합니다.
        # [EN] _get_array_like_types() builds the full type tuple once and caches it, avoiding per-call allocation.
        is_array_like = isinstance(content, _get_array_like_types())

        if container_like or is_array_like:
            # [KO] 실제 타입명을 동적으로 표시하고, 대표적인 차단 타입 예시를 비전체 힌트로 제공하여 디버깅을 돕습니다.
            # [EN] Show the actual type dynamically; add a non-exhaustive hint of common blocked types for easier debugging.
            raise TypeError(
                f"Document content must be a plain string or scalar value. "
                f"Got unsupported type {type(content).__name__!r} "
                f"(e.g. list, dict, ndarray, DataFrame, and Series are not supported)."
            )

        # Enum, Path 등 __str__이 유효한 단일(scalar) 객체는 문자열로 변환 허용
        return str(content)

    def __init__(
        self,
        dimension: Optional[int] = None,
        filter_expansion_factor: int = DEFAULT_FILTER_EXPANSION_FACTOR,
        persist_directory: Optional[Union[str, Path]] = None,
        load_on_init: bool = False,
    ):
        """
        [KO] FAISSRetriever 인스턴스를 초기화합니다.
        [EN] Initializes the FAISSRetriever instance.

        Args:
            dimension: [KO] 임베딩 벡터 차원 (기본값: ModelConfig 설정값) / [EN] Embedding vector dimension (defaults to ModelConfig)
            filter_expansion_factor: [KO] 메타데이터 필터링 시 FAISS에서 초기 추출할 후보군 배수 / [EN] Candidate expansion factor for metadata filtering
        """
        self.dimension = (
            ModelConfig.EMBEDDING_DIMENSION if dimension is None else dimension
        )
        self.index = faiss.IndexFlatL2(self.dimension)
        self.documents = []  # dict 객체 저장
        self.embedding_generator = EmbeddingGenerator()
        self.persist_directory = (
            Path(persist_directory) if persist_directory is not None else None
        )
        self._lock = threading.RLock()
        self.filter_expansion_factor = self._normalize_expansion_factor(
            filter_expansion_factor
        )
        if load_on_init and self.persist_directory is not None:
            self.load_if_available()

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

        embeddings_np = np.asarray(embeddings, dtype=np.float32)
        if embeddings_np.ndim != 2 or embeddings_np.shape[1] != self.dimension:
            raise ValueError("Embedding vectors do not match the configured dimension.")

        with self._lock:
            self.index.add(embeddings_np)  # type: ignore[call-arg]
            self.documents.extend(documents)
            self._persist_if_configured()

    def upsert_document(
        self,
        document_id: str,
        embedding: List[float],
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """문서 ID 기준으로 벡터를 추가하거나 교체하고 영속 저장한다."""
        if not document_id:
            raise ValueError("document_id is required.")
        vector = np.asarray([embedding], dtype=np.float32)
        if vector.shape != (1, self.dimension):
            raise ValueError(
                "Embedding vector does not match the configured dimension."
            )

        with self._lock:
            retained_documents = []
            retained_vectors = []
            for index, document in enumerate(self.documents):
                current_id = document.get("document_id") or (
                    document.get("metadata") or {}
                ).get("document_id")
                if current_id == document_id:
                    continue
                retained_documents.append(document)
                retained_vectors.append(self.index.reconstruct(index))

            self.index = faiss.IndexFlatL2(self.dimension)
            self.documents = retained_documents
            if retained_vectors:
                self.index.add(np.asarray(retained_vectors, dtype=np.float32))

            document = {
                "document_id": document_id,
                "content": content,
                "metadata": {**(metadata or {}), "document_id": document_id},
            }
            self.index.add(vector)
            self.documents.append(document)
            self._persist_if_configured()

    def get_embeddings(
        self,
        document_ids: List[str],
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, List[float]]:
        """저장된 문서 ID의 벡터를 반환하며 선택적으로 메타데이터를 필터링한다."""
        requested = set(document_ids)
        if not requested:
            return {}

        with self._lock:
            result: Dict[str, List[float]] = {}
            for index, document in enumerate(self.documents):
                metadata = document.get("metadata") or {}
                document_id = document.get("document_id") or metadata.get("document_id")
                if not isinstance(document_id, str) or document_id not in requested:
                    continue
                if metadata_filter and any(
                    metadata.get(key) != value for key, value in metadata_filter.items()
                ):
                    continue
                result[document_id] = self.index.reconstruct(index).tolist()
            return result

    def delete_documents(self, metadata_filter: Dict[str, Any]) -> int:
        """Remove all documents matching the complete metadata scope."""
        if not isinstance(metadata_filter, dict) or not metadata_filter:
            raise ValueError("A metadata filter is required for scoped deletion.")
        with self._lock:
            retained_documents = []
            retained_vectors = []
            removed_count = 0
            for index, document in enumerate(self.documents):
                metadata = document.get("metadata") or {}
                if check_metadata_match(metadata, metadata_filter):
                    removed_count += 1
                    continue
                retained_documents.append(document)
                retained_vectors.append(self.index.reconstruct(index))
            if removed_count:
                self.index = faiss.IndexFlatL2(self.dimension)
                self.documents = retained_documents
                if retained_vectors:
                    self.index.add(np.asarray(retained_vectors, dtype=np.float32))
                self._persist_if_configured()
            return removed_count

    def load_if_available(self) -> bool:
        """영속 인덱스가 있으면 로드하고, 최초 실행이면 False를 반환한다."""
        if self.persist_directory is None:
            return False
        if (
            not (self.persist_directory / "faiss.index").is_file()
            or not (self.persist_directory / "documents.json").is_file()
        ):
            return False
        self.load(self.persist_directory)
        return True

    def _persist_if_configured(self) -> None:
        if self.persist_directory is not None:
            self.save(self.persist_directory)

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

        with self._lock:
            if self.index.ntotal == 0:
                return []

        # 쿼리 임베딩 생성
        result = self.embedding_generator.generate_embeddings([query])
        embeddings = result.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != 1:
            raise ValueError("Embedding provider returned an unexpected query vector.")

        # NumPy 배열로 변환
        query_vector = np.asarray(embeddings, dtype=np.float32)
        if query_vector.shape != (1, self.dimension):
            raise ValueError(
                "Query embedding does not match the configured embedding dimension."
            )

        with self._lock:
            total = self.index.ntotal
            if total == 0:
                return []
            search_k = min(total, max(k, k * expansion if metadata_filter else k))
            results = []
            while search_k:
                # FAISS index and its position-aligned document list are read atomically.
                distances, indices = self.index.search(query_vector, search_k)  # type: ignore[call-arg]
                results = []
                for dist, idx in zip(distances[0], indices[0]):
                    if idx < 0 or idx >= len(self.documents):
                        continue
                    doc = self.documents[idx]
                    metadata = doc.get("metadata", {})
                    if metadata_filter and not check_metadata_match(
                        metadata, metadata_filter
                    ):
                        continue
                    results.append(
                        {
                            "content": doc.get("content", ""),
                            "metadata": (
                                dict(metadata)
                                if isinstance(metadata, dict)
                                else metadata
                            ),
                            "score": 1 / (1 + float(dist)),
                            "distance": float(dist),
                        }
                    )
                    if len(results) >= k:
                        return results
                if search_k >= total:
                    break
                search_k = min(total, search_k * 2)
            return results

    def clear(self):
        """
        [KO] FAISS 인덱스와 저장된 문서를 모두 초기화합니다.
        [EN] Clears the FAISS index and all stored documents.
        """
        with self._lock:
            self.index = faiss.IndexFlatL2(self.dimension)
            self.documents = []
            self._persist_if_configured()

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

        with self._lock:
            faiss.write_index(self.index, str(directory / "faiss.index"))
            with open(directory / "documents.json", "w", encoding="utf-8") as f:
                json.dump(self.documents, f, ensure_ascii=False, indent=2)

        logger.info("FAISS 인덱스 및 메타데이터 저장 완료")

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

        with self._lock:
            loaded_index = faiss.read_index(str(index_path))
            with open(docs_path, "r", encoding="utf-8") as f:
                loaded_documents = json.load(f)
            if (
                not isinstance(loaded_documents, list)
                or any(not isinstance(document, dict) for document in loaded_documents)
                or loaded_index.ntotal != len(loaded_documents)
            ):
                raise ValueError("FAISS index and document metadata are inconsistent.")
            if loaded_index.d != self.dimension:
                raise ValueError(
                    "Persisted FAISS index dimension does not match the configured embedding dimension."
                )
            self.index = loaded_index
            self.documents = loaded_documents

        logger.info(
            "FAISS 인덱스 및 메타데이터 로드 완료: %d개 문서", len(self.documents)
        )


_PERSISTENT_RETRIEVER: Optional[FAISSRetriever] = None
_PERSISTENT_RETRIEVER_LOCK = threading.Lock()


def get_persistent_retriever(refresh: bool = False) -> FAISSRetriever:
    """PathConfig의 공유 인덱스를 복원해 반환한다.

    별도 Celery/MCP 프로세스가 쓴 최신 데이터가 필요한 호출자는 refresh를 지정한다.
    """
    global _PERSISTENT_RETRIEVER
    if _PERSISTENT_RETRIEVER is None:
        with _PERSISTENT_RETRIEVER_LOCK:
            if _PERSISTENT_RETRIEVER is None:
                from backend.config import ModelConfig, PathConfig

                _PERSISTENT_RETRIEVER = FAISSRetriever(
                    dimension=ModelConfig.EMBEDDING_DIMENSION,
                    persist_directory=PathConfig.FAISS_INDEX_DIR,
                    load_on_init=True,
                )
    if refresh and _PERSISTENT_RETRIEVER.persist_directory is not None:
        with _PERSISTENT_RETRIEVER_LOCK:
            _PERSISTENT_RETRIEVER.load_if_available()
    return _PERSISTENT_RETRIEVER


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
    # 서브클래싱 및 인스턴스별 동작 오버라이딩을 지원하기 위해 인스턴스 메서드로 호출합니다.
    texts = [retriever._validate_content(doc.get("content")) for doc in docs]

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
