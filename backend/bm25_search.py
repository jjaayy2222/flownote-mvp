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

    def __init__(self, tokenizer: Optional[Callable[[str], List[str]]] = None):
        self.bm25: Optional[BM25Okapi] = None
        self.documents: List[Dict] = []
        self.tokenizer = tokenizer or self._default_tokenize

    def _default_tokenize(self, text: str) -> List[str]:
        """간단한 띄어쓰기 기반 토크나이징"""
        if not text or not isinstance(text, str):
            return []
        # 영문의 경우 소문자화하여 검색 품질을 높임
        return text.strip().lower().split()

    def add_documents(self, documents: List[Dict[str, Any]]):
        """
        문서 추가 및 BM25 인덱스 빌드

        Args:
            documents: 문서 dict 리스트 (content, metadata 포함)
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

        # NOTE:
        # 현재 구현은 문서가 추가될 때마다 전체 코퍼스를 기반으로 BM25 인덱스를
        # 다시 빌드합니다. 이는 O(N) 동작이며, 상대적으로 작은/거의 정적인 코퍼스를
        # 대상으로 하는 간단한 구현입니다. 더 큰 코퍼스나 잦은 업데이트가 필요한
        # 경우에는 별도의 `build_index()` 단계와 배치 추가 전략을 고려해야 합니다.
        corpus = [self.tokenizer(doc.get("content", "")) for doc in self.documents]
        self.bm25 = BM25Okapi(corpus)
        logger.info("BM25 인덱스 빌드 완료 (총 %d개 문서)", len(self.documents))

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
        if query is not None:
            query = query.strip()

        if not self.bm25 or not self.documents or not query:
            return []

        tokenized_query = self.tokenizer(query)
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
