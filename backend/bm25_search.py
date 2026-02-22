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
from typing import List, Dict, Optional, Any, Callable
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


class BM25Retriever:
    """BM25 (Rank BM25) 기반 희소 벡터(키워드) 검색"""

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
                hint = (
                    doc_metadata.get("source", "unknown") if doc_metadata else "unknown"
                )
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

    def _rebuild_index(self):
        """현재 저장된 문서를 기반으로 BM25 인덱스를 재구성합니다."""
        if not self.documents:
            self.bm25 = None
            return

        # NOTE:
        # 현재 구현은 리빌드 호출 시 전체 코퍼스를 기반으로 BM25 인덱스를 재구성합니다.
        # 대량의 문서가 업데이트될 경우 add_documents(..., rebuild=False) 호출 후
        # 마지막에 build_index()를 한 번만 호출하는 배치 처리를 권장합니다.
        corpus = [
            self._safe_tokenize(
                doc.get("content", ""), doc_metadata=doc.get("metadata", {})
            )
            for doc in self.documents
        ]
        self.bm25 = BM25Okapi(corpus)
        logger.info("BM25 인덱스 빌드 완료 (총 %d개 문서)", len(self.documents))

    def build_index(self):
        """명시적으로 BM25 인덱스를 (재)빌드합니다. 배치 업데이트 후 사용하세요."""
        self._rebuild_index()

    def add_documents(self, documents: List[Dict[str, Any]], rebuild: bool = True):
        """
        문서 추가 및 BM25 인덱스 빌드

        Args:
            documents: 문서 dict 리스트 (content, metadata 포함)
            rebuild: 문서 추가 후 즉시 인덱스를 재빌드할지 여부
        """
        if not documents:
            return

        valid_docs = [
            doc for doc in documents if isinstance(doc, dict) and "content" in doc
        ]
        if not valid_docs:
            logger.warning("유효한 문서가 없습니다.", extra={"context": len(documents)})
            return

        self.documents.extend(valid_docs)
        if rebuild:
            self._rebuild_index()

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

    retriever.add_documents(docs)

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
