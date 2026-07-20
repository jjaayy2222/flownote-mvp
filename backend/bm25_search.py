# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/bm25_search.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
[KO] FlowNote MVP - BM25 희소 벡터(키워드) 검색
[EN] FlowNote MVP - BM25 Sparse Vector (Keyword) Search

주의 / Note:
    [KO] 현재 구현은 `add_documents` 호출 시마다 전체 BM25 인덱스를 재구성합니다.
    [EN] The current implementation rebuilds the entire BM25 index on every `add_documents` call.
    [KO] 이는 O(N) 동작이며, 상대적으로 작은 규모의 코퍼스나 업데이트가 많지 않은
    [EN] This is an O(N) operation, designed for relatively small corpora or
         nearly-static corpora with infrequent updates.
    [KO] 대규모 또는 고빈도 업데이트가 필요한 경우, 배치 추가 후 명시적으로 인덱스를
    [EN] For large-scale or high-frequency updates, consider a separate workflow
         빌드하는 별도 워크플로우를 고려하세요.
         that builds the index explicitly after batch additions.
"""

import json
import logging
import pickle
from collections.abc import Mapping
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Tuple,
    TypedDict,
    Union,
)

from rank_bm25 import BM25Okapi

from backend.utils import check_metadata_match

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_MAX_VISIBLE = 3


class FilterStats(TypedDict):
    """
    [KO] 문서 필터링 과정에서 수집된 통계와 샘플 데이터.
    [EN] Statistics and sample data collected during document filtering.
    """

    removed_invalid_type: int
    removed_empty_token: int
    invalid_samples: List[str]
    empty_samples: List[str]


class RebuildStats(TypedDict):
    """
    [KO] 인덱스 재구축 시 영구 제외된 문서 통계.
    [EN] Statistics of permanently excluded documents during index rebuild.
    """

    removed_invalid_type: int
    removed_empty_token: int


class AddDocumentsStats(TypedDict):
    """
    [KO] 문서 추가 작업 결과 통계.
    [EN] Statistics of the document addition operation result.
    """

    rejected_format: int
    rebuild_stats: Optional[RebuildStats]


def _format_samples(samples: List[str], total_count: int, max_visible: int) -> str:
    """
    [KO] 로그에 출력할 샘플 리스트 문자열을 포맷팅하는 헬퍼 함수입니다.
    [EN] Helper function to format sample lists for log output.

    Args:
        samples: [KO] 포맷팅할 샘플 문자열 리스트 / [EN] List of sample strings to format
        total_count: [KO] 전체 샘플 총 개수 / [EN] Total number of samples
        max_visible: [KO] 로그에 표시할 최대 샘플 수 / [EN] Maximum number of samples to display

    Returns:
        str: [KO] 지정된 개수를 초과하면 '...'이 붙는 포맷된 문자열 / [EN] Formatted string with '...' appended if count exceeds max_visible
    """
    samples_str = ", ".join(samples[:max_visible])
    if total_count > max_visible:
        samples_str += ", ..."
    return samples_str


class BM25Retriever:
    """
    [KO] BM25 (Rank BM25) 기반 희소 벡터(키워드) 검색기입니다.
    [EN] BM25 (Rank BM25)-based sparse vector (keyword) retriever.

    주의 (Side-Effect) / Note:
        [KO] 내부 무결성 보장을 위해, 인덱스를 재빌드(rebuild)할 때
        [EN] To maintain internal consistency, when rebuilding the index,
        [KO] 비정상적인 형식의 데이터나 유효한 키워드 토큰을 생성하지 못하는(비어있는) 문서는
        [EN] documents with invalid formats or those that produce no valid keyword tokens
        [KO] 상위 호출자의 의도와 상관없이 `self.documents` 배열 리스트에서 영구적으로 제외(Filter-out)됩니다.
        [EN] are permanently excluded from `self.documents` regardless of the caller's intent.
    """

    def __init__(
        self,
        tokenizer: Optional[Callable[[str], Iterable[str]]] = None,
        coerce_all_strings: bool = False,
    ):
        """
        [KO] BM25 검색 엔진을 초기화합니다.
        [EN] Initializes the BM25 search engine.

        Args:
            tokenizer: [KO] 사용자 지정 토크나이저. 반환되는 이터러블/제너레이터는 즉시 `list()`로 소비됩니다. / [EN] Custom tokenizer. Returned iterables/generators are immediately consumed with `list()`.
            coerce_all_strings: [KO] `dict`나 `list` 등 비문자열 객체가 content로 들어왔을 때, 조용히 건너뛰지 않고 무조건 `str()`로 강제 변환할지 여부. / [EN] Whether to forcibly cast non-string content to `str()` instead of silently skipping it.
        """
        self.bm25: Optional[BM25Okapi] = None
        self.documents: List[Dict[str, Any]] = []
        self.coerce_all_strings = coerce_all_strings
        self.tokenizer: Callable[[str], Iterable[str]]

        # 외부 토크나이저 주입 처리 방어
        if tokenizer is not None and callable(tokenizer):
            self.tokenizer = tokenizer
        else:
            if tokenizer is not None:
                logger.warning(
                    "제공된 토크나이저가 호출 가능하지 않습니다. 기본 토크나이저를 사용합니다."
                )
            self.tokenizer = self._default_tokenize

    def _default_tokenize(self, text: str) -> List[str]:
        """
        [KO] 간단한 띄어쓰기 기반 토크나이징 기본 구현입니다.
        [EN] Simple whitespace-based tokenization (default implementation).
        """
        # _safe_tokenize에서 이미 str 타입 여부 및 빈 문자열을 검증하므로 바로 처리
        return text.lower().split()

    def _safe_tokenize(
        self, text: Any, doc_metadata: Optional[Dict] = None
    ) -> List[str]:
        """
        [KO] 텍스트를 받아 안전하게 토크나이징을 수행하는 헬퍼 메서드입니다.
        [EN] Helper method that safely tokenizes text with fallback handling.

        Args:
            text: [KO] 토크나이징할 텍스트 (str 보장 없음) / [EN] Text to tokenize (not guaranteed to be str)
            doc_metadata: [KO] 로그 힌트 생성용 문서 메타데이터 (Optional) / [EN] Document metadata used to generate log hints (Optional)

        Returns:
            List[str]: [KO] 토큰 리스트. 비정상 입력 또는 빈 문자열인 경우 빈 리스트([]) 반환. / [EN] List of tokens. Returns empty list ([]) for invalid input or empty text.
        """
        if not isinstance(text, str):
            # 스칼라(숫자, 불리언)이거나 설정 상 강제 문자열 변환이 켜져있을 경우
            if self.coerce_all_strings or isinstance(text, (int, float, bool)):
                text = str(text) if text is not None else ""
            else:
                hint = "unknown"
                if isinstance(doc_metadata, Mapping):
                    hint = doc_metadata.get("source", "unknown")
                logger.warning(
                    "문자열 또는 단순 스칼라 값이 아닌 데이터가 포함되어 토크나이징을 건너뜁니다. (coerce_all_strings=True 필요)",
                    extra={"context": type(text).__name__, "doc_source": hint},
                )
                return []

        text = text.strip()
        if not text:
            return []

        try:
            tokens = self.tokenizer(text)

            # 토크나이저가 문자열을 반환하면 list('text') -> ['t', 'e', 'x', 't'] 로 산산조각 나는 것을 방지
            if isinstance(tokens, (str, bytes)):
                logger.warning(
                    "토크나이저 반환값이 문자열/바이트입니다. 문자 단위 분해가 일어나지 않도록 기본 토크나이저로 대체합니다.",
                    extra={"context": type(tokens).__name__},
                )
                return self._default_tokenize(text)

            try:
                tokens = list(tokens)
            except TypeError:
                logger.warning(
                    "토크나이저 반환값을 이터러블(list)로 변환할 수 없습니다. 기본 토크나이저로 대체합니다.",
                    extra={"context": type(tokens).__name__},
                )
                return self._default_tokenize(text)
            return tokens
        except Exception as e:
            logger.exception(
                "토크나이징 중 예상치 못한 에러가 발생했습니다. 기본 토크나이저로 대체합니다.",
                extra={"context": type(e).__name__},
            )
            return self._default_tokenize(text)

    def _filter_documents_for_index(
        self,
    ) -> Tuple[List[Dict[str, Any]], List[List[str]], FilterStats]:
        """
        [KO] 인덱스 생성을 위한 유효 문서를 필터링하고 통계를 수집합니다.
        [EN] Filters valid documents for index construction and collects statistics.

        Returns:
            Tuple[List[Dict[str, Any]], List[List[str]], FilterStats]:
                [KO] (유효 문서 리스트, 토큰화된 코퍼스, 필터링 통계) 튜플 /
                [EN] Tuple of (valid document list, tokenized corpus, filter statistics)
        """
        valid_docs: List[Dict[str, Any]] = []
        corpus: List[List[str]] = []
        invalid_type_count = 0
        empty_count = 0
        invalid_samples: List[str] = []
        empty_samples: List[str] = []

        for doc in self.documents:
            # 레거시 데이터나 외부 강제 주입 방어
            if not isinstance(doc, dict):
                invalid_type_count += 1
                if len(invalid_samples) < 3:
                    invalid_samples.append(type(doc).__name__)
                continue

            metadata = doc.get("metadata", {})
            tokens = self._safe_tokenize(doc.get("content", ""), doc_metadata=metadata)

            if not tokens:
                empty_count += 1
                if len(empty_samples) < 3:
                    hint = (
                        metadata.get("source", "unknown")
                        if isinstance(metadata, Mapping)
                        else "unknown"
                    )
                    empty_samples.append(str(hint))
                continue

            valid_docs.append(doc)
            corpus.append(tokens)

        stats: FilterStats = {
            "removed_invalid_type": invalid_type_count,
            "removed_empty_token": empty_count,
            "invalid_samples": invalid_samples,
            "empty_samples": empty_samples,
        }
        return valid_docs, corpus, stats

    def _rebuild_index(self) -> RebuildStats:
        """
        [KO] [내부 헬퍼 메서드] 현재 저장된 문서를 기반으로 BM25 인덱스를 재구성합니다.
        [EN] [Internal helper] Rebuilds the BM25 index from the currently stored documents.

        주의 / Note:
            [KO] 이 메서드는 유효한 키워드가 없는 문서나 딕셔너리가 아닌 항목을
            [EN] This method permanently filters and removes from `self.documents`
            [KO] `self.documents` 리스트에서 영구적으로 필터링 및 제거 변경(mutate)합니다.
            [EN] any documents without valid keywords or non-dict entries.
            [KO] 외부 호출자는 명시적 빌드가 필요한 경우 public API인 `build_index()`를 사용하세요.
            [EN] External callers should use the public API `build_index()` when explicit builds are needed.

        Returns:
            RebuildStats: [KO] 필터링 과정에서 제거된 문서들의 통계 딕셔너리. /
                         [EN] Statistics dictionary of documents removed during filtering.
        """
        stats: RebuildStats = {
            "removed_invalid_type": 0,
            "removed_empty_token": 0,
        }

        if not self.documents:
            self.bm25 = None
            return stats

        valid_docs, corpus_tokens, filter_stats = self._filter_documents_for_index()
        self.documents = valid_docs

        stats["removed_invalid_type"] = filter_stats["removed_invalid_type"]
        stats["removed_empty_token"] = filter_stats["removed_empty_token"]

        if stats["removed_invalid_type"] > 0:
            logger.warning(
                "딕셔너리(dict) 타입이 아닌 비정상 항목 %d개를 인덱스 재빌드 과정에서 영구 제외했습니다. (샘플: %s)",
                stats["removed_invalid_type"],
                _format_samples(
                    filter_stats["invalid_samples"],
                    stats["removed_invalid_type"],
                    DEFAULT_SAMPLE_MAX_VISIBLE,
                ),
            )

        if stats["removed_empty_token"] > 0:
            logger.warning(
                "유효한 키워드 토큰이 없는 문서 %d개를 인덱스에서 제외했습니다. (샘플 출처: %s)",
                stats["removed_empty_token"],
                _format_samples(
                    filter_stats["empty_samples"],
                    stats["removed_empty_token"],
                    DEFAULT_SAMPLE_MAX_VISIBLE,
                ),
            )

        if not corpus_tokens:
            self.bm25 = None
            return stats

        self.bm25 = BM25Okapi(corpus_tokens)
        logger.info("BM25 인덱스 빌드 완료 (총 %d개 문서)", len(self.documents))
        return stats

    def build_index(self) -> RebuildStats:
        """
        [KO] 명시적으로 BM25 인덱스를 (재)빌드합니다. 배치 업데이트 후 사용하세요.
        [EN] Explicitly (re)builds the BM25 index. Use after batch updates.

        Returns:
            RebuildStats: [KO] 재빌드 과정에서 필터링 및 제외된 문서들의 통계 결과 / [EN] Statistics of documents filtered and excluded during the rebuild
        """
        return self._rebuild_index()

    def add_documents(
        self, documents: List[Dict[str, Any]], rebuild: bool = True
    ) -> AddDocumentsStats:
        """
        [KO] 문서 추가 및 BM25 인덱스 빌드를 수행합니다.
        [EN] Adds documents and (re)builds the BM25 index.

        주의 / Note:
            [KO] 성공적으로 추가된 문서라 하더라도, `rebuild=True`에 의해 즉시 실행되거나 향후
            [EN] Even successfully added documents may be silently removed during index
            [KO] `build_index()`에 의해 실행되는 인덱스 재구성 과정에서 유효한 검색 토큰(단어)를
            [EN] reconstruction triggered by `rebuild=True` or a future `build_index()` call,
            [KO] 만들어내지 못하는 문서들은 `self.documents` 배열에서 조용히 제거(Filter-out)됩니다.
            [EN] if they produce no valid keyword tokens.

        Args:
            documents: [KO] 문서 dict 리스트 (content, metadata 포함) / [EN] List of document dicts (including content, metadata)
            rebuild: [KO] 문서 추가 후 즉시 인덱스를 재빌드할지 여부 / [EN] Whether to immediately rebuild the index after adding documents

        Returns:
            AddDocumentsStats:
                [KO] 추가 및 재빌드 과정에서 제거된 처리 통계를 담은 딕셔너리. /
                [EN] Dictionary containing processing statistics of removed docs during addition and rebuild.
                [KO] `rebuild_stats`가 `None`인 경우: 인덱스 재빌드가 수행되지 않음 (예: `rebuild=False`이거나 추가된 문서가 없음).
                [EN] `rebuild_stats` is `None`: no index rebuild was performed (e.g. `rebuild=False` or no documents added).
                [KO] `rebuild_stats`가 dict인 경우: 재빌드를 수행했고, 그 결과 통계를 담고 있음.
                [EN] `rebuild_stats` is a dict: a rebuild was performed and contains its result statistics.
        """
        stats: AddDocumentsStats = {"rejected_format": 0, "rebuild_stats": None}
        if not documents:
            return stats

        initial_count = len(documents)
        valid_docs: List[Dict[str, Any]] = []
        rejected_samples: List[str] = []

        for doc in documents:
            if isinstance(doc, dict) and "content" in doc:
                valid_docs.append(doc)
            elif len(rejected_samples) < 3:
                if isinstance(doc, dict):
                    metadata = doc.get("metadata")
                    hint = (
                        metadata.get("source", "unknown")
                        if isinstance(metadata, Mapping)
                        else "unknown"
                    )
                    rejected_samples.append(f"Content missing (source: {hint})")
                else:
                    rejected_samples.append(type(doc).__name__)

        rejected_count = initial_count - len(valid_docs)
        stats["rejected_format"] = rejected_count

        if rejected_count > 0:
            logger.warning(
                "형식이 잘못된 문서 %d개를 추가 대상에서 제외했습니다. 샘플: %s",
                rejected_count,
                _format_samples(
                    rejected_samples, rejected_count, DEFAULT_SAMPLE_MAX_VISIBLE
                ),
            )

        if not valid_docs:
            logger.warning("유효한 문서가 없어 추가 작업을 건너뜁니다.")
            return stats

        self.documents.extend(valid_docs)
        if rebuild:
            stats["rebuild_stats"] = self._rebuild_index()

        return stats

    def search(
        self,
        query: str,
        k: int = 3,
        filter_zero_score: bool = True,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        [KO] 쿼리에 가장 유사한 문서를 검색합니다.
        [EN] Searches for documents most similar to the given query.

        Args:
            query: [KO] 검색 쿼리 문자열 / [EN] The search query string
            k: [KO] 반환할 최대 결과 수 / [EN] Maximum number of results to return
            filter_zero_score: [KO] BM25 점수가 0인 문서(연관성 없음)를 필터링할지 여부 / [EN] Whether to filter out documents with a BM25 score of 0 (no relevance)
            metadata_filter: [KO] 메타데이터 필터 조건 (예: {"category": "Projects"}) / [EN] Metadata filter condition dictionary (e.g. {"category": "Projects"})

        Returns:
            List[Dict[str, Any]]: [KO] 검색 결과 리스트 (content, metadata, score 포함) / [EN] List of search results (including content, metadata, score)
        """
        if not isinstance(query, str):
            logger.warning(
                "검색 쿼리가 문자열이 아닙니다. 문자열로 변환하여 처리합니다.",
                extra={"context": type(query).__name__},
            )
            if query is None:
                query = ""
            else:
                query = f"{query}"

        query = query.strip()
        if not self.bm25 or not self.documents or not query:
            return []

        tokenized_query = self._safe_tokenize(query)
        # Avoid meaningless searches on empty token lists
        if not tokenized_query:
            return []

        doc_scores = self.bm25.get_scores(tokenized_query)

        # 필터링 적용할 대상 인덱스 추출
        candidate_indices = range(len(doc_scores))
        if metadata_filter:
            candidate_indices = [
                i
                for i in candidate_indices
                if check_metadata_match(
                    self.documents[i].get("metadata", {}), metadata_filter
                )
            ]

        # 높은 점수 순으로 정렬 (필터링된 후보군 내에서 k개 추출)
        top_k_indices = sorted(
            candidate_indices, key=lambda i: doc_scores[i], reverse=True
        )[:k]

        results = []
        for idx in top_k_indices:
            score = float(doc_scores[idx])
            if filter_zero_score and score <= 0.0:
                continue

            doc = self.documents[idx]
            results.append(
                {
                    "content": doc.get("content", ""),
                    "metadata": doc.get("metadata", {}),
                    "score": score,
                    # distance 필드는 하이브리드 RRF 레이어 구현 시 혼선의 원인(zero-distance-hack)이 될 수 있어 제거됨
                }
            )

        return results

    def clear(self):
        """
        [KO] BM25 인덱스와 저장된 문서를 모두 초기화합니다.
        [EN] Clears the BM25 index and all stored documents.
        """
        self.bm25 = None
        self.documents = []

    def size(self) -> int:
        """
        [KO] 인덱스에 저장된 문서의 총 개수를 반환합니다.
        [EN] Returns the total number of documents stored in the index.

        Returns:
            int: [KO] 저장된 문서 수 / [EN] The number of stored documents
        """
        return len(self.documents)

    def save(self, directory: Union[str, Path]) -> None:
        """
        [KO] 인덱스와 메타데이터를 지정된 디렉토리에 저장합니다.
        [EN] Saves the index and metadata to the specified directory.

        Args:
            directory: [KO] 저장할 디렉토리 경로 / [EN] The directory path to save to
        """
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)

        # 1. 문서 데이터 저장 (JSON)
        with open(directory / "documents.json", "w", encoding="utf-8") as f:
            json.dump(self.documents, f, ensure_ascii=False, indent=2)

        # 2. BM25 객체 저장 (Pickle)
        with open(directory / "bm25.pkl", "wb") as f:
            pickle.dump(self.bm25, f)

        logger.info("BM25 인덱스 및 메타데이터 저장 완료: %s", directory)

    def load(self, directory: Union[str, Path]) -> None:
        """
        [KO] 지정된 디렉토리에서 인덱스와 메타데이터를 로드합니다.
        [EN] Loads the index and metadata from the specified directory.

        Args:
            directory: [KO] 로드할 파일이 있는 디렉토리 경로 / [EN] The directory path to load from
        """
        directory = Path(directory)
        docs_path = directory / "documents.json"
        index_path = directory / "bm25.pkl"

        if not docs_path.exists() or not index_path.exists():
            raise FileNotFoundError(f"BM25 index files not found in {directory}")

        # 1. 문서 데이터 로드
        with open(docs_path, "r", encoding="utf-8") as f:
            self.documents = json.load(f)

        # 2. BM25 객체 로드
        with open(index_path, "rb") as f:
            self.bm25 = pickle.load(f)

        logger.info(
            "BM25 인덱스 및 메타데이터 로드 완료: %d개 문서", len(self.documents)
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger.info("=" * 50)
    logger.info("BM25 검색 테스트")
    logger.info("=" * 50)

    retriever = BM25Retriever()

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

    # 문서 추가 및 인덱스 빌드 수행
    # 반환되는 통계(AddDocumentsStats)는 테스트 목적상 로그로 이미 확인되므로 여기선 명시적으로 무시합니다.
    _ = retriever.add_documents(docs)

    query = "대화를 어떻게 관리하나요"
    logger.info("\n🔍 검색 쿼리: '%s'", query)
    results = retriever.search(query, k=2)

    logger.info("\n검색 결과 (%d개):", len(results))
    logger.info("-" * 50)
    for i, result in enumerate(results, 1):
        logger.info("\n%d위:", i)
        logger.info("    - 점수: %.4f", result["score"])
        # 보안 측면을 고려하여 테스트 로그에서도 내용의 일부만 마스킹하여 출력
        content_preview = result.get("content", "")[:15] + (
            "..." if len(result.get("content", "")) > 15 else ""
        )
        logger.info("    - 내용: %s", content_preview)
        logger.info(
            "    - 출처: %s", result.get("metadata", {}).get("source", "unknown")
        )

    logger.info("\n" + "=" * 50)
