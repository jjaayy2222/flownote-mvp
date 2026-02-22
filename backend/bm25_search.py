# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/bm25_search.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - BM25 희소 벡터(키워드) 검색

주의:
- 현재 구현은 `add_documents` 호출 시마다 전체 BM25 인덱스를 재구성합니다.
- 이는 O(N) 동작이며, 상대적으로 작은 규모의 코퍼스나 업데이트가 많지 않은
  거의 정적인 코퍼스를 대상으로 설계되었습니다.
- 대규모 또는 고빈도 업데이트가 필요한 경우, 배치 추가 후 명시적으로 인덱스를
  빌드하는 별도 워크플로우를 고려하세요.
"""

import logging
from collections.abc import Mapping
from typing import (
    List,
    Dict,
    Optional,
    Any,
    Callable,
    Tuple,
    TypedDict,
)
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_MAX_VISIBLE = 3


class FilterStats(TypedDict):
    """문서 필터링 과정에서 수집된 통계와 샘플 데이터."""

    removed_invalid_type: int
    removed_empty_token: int
    invalid_samples: List[str]
    empty_samples: List[str]


class RebuildStats(TypedDict):
    """인덱스 재구축 시 영구 제외된 문서 통계."""

    removed_invalid_type: int
    removed_empty_token: int


class AddDocumentsStats(TypedDict):
    """문서 추가 작업 결과 통계."""

    rejected_format: int
    rebuild_stats: Optional[RebuildStats]


def _format_samples(samples: List[str], total_count: int, max_visible: int) -> str:
    """로그에 출력할 샘플 리스트 문자열 포맷팅 헬퍼. 정해진 개수를 초과하면 '...'을 붙입니다."""
    samples_str = ", ".join(samples[:max_visible])
    if total_count > max_visible:
        samples_str += ", ..."
    return samples_str


class BM25Retriever:
    """
    BM25 (Rank BM25) 기반 희소 벡터(키워드) 검색

    주의 (Side-Effect):
        내부 무결성 보장을 위해, 인덱스를 재빌드(rebuild)할 때
        비정상적인 형식의 데이터나 유효한 키워드 토큰을 생성하지 못하는(비어있는) 문서는
        상위 호출자의 의도와 상관없이 `self.documents` 배열 리스트에서 영구적으로 제외(Filter-out)됩니다.
    """

    def __init__(
        self,
        tokenizer: Optional[Callable[[str], List[str]]] = None,
        coerce_all_strings: bool = False,
    ):
        """
        BM25 검색 엔진 초기화

        Args:
            tokenizer: 사용자 지정 토크나이저. 반환되는 이터러블/제너레이터는 즉시 `list()`로 소비됩니다.
            coerce_all_strings: `dict`나 `list` 등 비문자열 객체가 content로 들어왔을 때, 조용히 건너뛰지 않고 무조건 `str()`로 강제 변환할지 여부.
        """
        self.bm25: Optional[BM25Okapi] = None
        self.documents: List[Dict[str, Any]] = []
        self.coerce_all_strings = coerce_all_strings

        # 외부 토크나이저 주입 처리 방어
        if tokenizer is not None and not callable(tokenizer):
            logger.warning(
                "제공된 토크나이저가 호출 가능하지 않습니다. 기본 토크나이저를 사용합니다."
            )
            self.tokenizer = self._default_tokenize
        else:
            self.tokenizer = tokenizer or self._default_tokenize

    def _default_tokenize(self, text: str) -> List[str]:
        """간단한 띄어쓰기 기반 토크나이징"""
        # _safe_tokenize에서 이미 str 타입 여부 및 빈 문자열을 검증하므로 바로 처리
        return text.lower().split()

    def _safe_tokenize(
        self, text: Any, doc_metadata: Optional[Dict] = None
    ) -> List[str]:
        """텍스트를 받아 안전하게 토크나이징을 수행하는 헬퍼 메서드"""
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
        인덱스 생성을 위한 유효 문서를 필터링하고 통계를 수집합니다.
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
        [내부 헬퍼 메서드] 현재 저장된 문서를 기반으로 BM25 인덱스를 재구성합니다.

        주의:
            이 메서드는 유효한 키워드가 없는 문서나 딕셔너리가 아닌 항목을
            `self.documents` 리스트에서 영구적으로 필터링 및 제거 변경(mutate)합니다.
            외부 호출자는 명시적 빌드가 필요한 경우 public API인 `build_index()`를 사용하세요.

        Returns:
            RebuildStats: 필터링 과정에서 제거된 문서들의 통계 딕셔너리.
            주의: 이 통계는 `add_documents` 내부에서 처리 결과를 병합하는 데 사용되거나,
            public API인 `build_index()` 호출 시 반환되어 외부 관측성(Observability)을 위해 활용됩니다.
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
        명시적으로 BM25 인덱스를 (재)빌드합니다. 배치 업데이트 후 사용하세요.

        Returns:
            재빌드 과정에서 필터링 및 제외된 문서들의 통계 결과
        """
        return self._rebuild_index()

    def add_documents(
        self, documents: List[Dict[str, Any]], rebuild: bool = True
    ) -> AddDocumentsStats:
        """
        문서 추가 및 BM25 인덱스 빌드

        주의:
            성공적으로 추가된 문서라 하더라도, `rebuild=True`에 의해 즉시 실행되거나 향후
            `build_index()`에 의해 실행되는 인덱스 재구성 과정에서 유효한 검색 토큰(단어)을
            만들어내지 못하는 문서들은 `self.documents` 배열에서 조용히 제거(Filter-out)됩니다.

        Args:
            documents: 문서 dict 리스트 (content, metadata 포함)
            rebuild: 문서 추가 후 즉시 인덱스를 재빌드할지 여부

        Returns:
            추가 및 재빌드 과정에서 제거된 처리 통계를 담은 딕셔너리.

            - `rebuild_stats` 가 `None` 인 경우: 인덱스 재빌드가 수행되지 않음
              (예: `rebuild=False` 이거나 추가된 문서가 없음).
            - `rebuild_stats` 가 dict 인 경우: 재빌드를 수행했고, 그 결과 통계를 담고 있음.
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
            else:
                if len(rejected_samples) < 3:
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
        self, query: str, k: int = 3, filter_zero_score: bool = True
    ) -> List[Dict[str, Any]]:
        """
        쿼리에 가장 유사한 문서 검색

        Args:
            query: 검색 쿼리
            k: 반환할 결과 수
            filter_zero_score: 점수가 0인 문서(연관성 없음)를 필터링할지 여부

        Returns:
            검색 결과 리스트 (content, metadata, score 포함)
        """
        if not isinstance(query, str):
            logger.warning(
                "검색 쿼리가 문자열이 아닙니다. 문자열로 변환하여 처리합니다.",
                extra={"context": type(query).__name__},
            )
            query = str(query) if query is not None else ""

        query = query.strip()
        if not self.bm25 or not self.documents or not query:
            return []

        tokenized_query = self._safe_tokenize(query)
        # Avoid meaningless searches on empty token lists
        if not tokenized_query:
            return []

        doc_scores = self.bm25.get_scores(tokenized_query)

        # 높은 점수 순으로 정렬
        top_k_indices = sorted(
            range(len(doc_scores)), key=lambda i: doc_scores[i], reverse=True
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
        """인덱스 초기화"""
        self.bm25 = None
        self.documents = []

    def size(self) -> int:
        """인덱스에 저장된 문서 수"""
        return len(self.documents)


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
