# RAG Search Tuning Guide

본 문서는 FlowNote MVP의 하이브리드 검색(Hybrid Search) 성능 최적화를 위한 파라미터 튜닝 가이드를 제공합니다.

## 1. 개요
하이브리드 검색은 FAISS(Dense Vector)와 BM25(Sparse Vector) 결과를 RRF(Reciprocal Rank Fusion)로 병합합니다. 메타데이터 필터링이 적용될 경우, 초기 검색 단계에서 충분한 후보군을 확보하지 못하면 최종 결과의 재현율(Recall)이 저하될 수 있습니다.

## 2. 주요 파라미터: `filter_expansion_factor`

### 역할
- **FAISS/BM25 검색 후보군 확장**: 메타데이터 필터링이 적용된 검색에서, 초기 검색 결과가 필터에 의해 걸러져 최종 결과 `k`개를 채우지 못하는 문제를 방지하기 위해 후보군을 `k * filter_expansion_factor`만큼 늘려서 가져옵니다.
- **조건부 적용**: 이 파라미터는 **메타데이터 필터(`metadata_filter` 또는 `category`)가 제공될 때만** 유효하며, 필터가 없는 일반 검색에서는 시스템 부하를 줄이기 위해 자동으로 `1`로 처리됩니다.
- **재현율 보장**: 필터 조건이 까다로운 경우(예: 특정 날짜의 특정 프로젝트 문서만 검색), 후보군을 크게 잡아야 필터링 후에도 사용자가 요청한 `k`개의 결과를 충분히 확보할 수 있습니다.

### 설정 가이드
- **기본값**: `2`
- **권장 범위**: `1` ~ `20`
- **주의사항**:
  - `faiss_k` 또는 `bm25_k`를 직접 명시적으로 전달하는 경우, `filter_expansion_factor` 계수는 무시됩니다. 
- **튜닝 전략**:
  - 필터링을 자주 사용하고, 특정 카테고리의 문서 비중이 낮은 경우: `5` ~ `10` 권장.
  - 성능(응답 속도)이 중요하고 필터링 조건이 느슨한 경우: `1` ~ `2` 권장.

## 3. 실험 결과 (2026-03-01 측정)
`tests/e2e/test_rag_search_quality.py`를 통해 실제 OpenAI `text-embedding-3-small` 임베딩으로 측정한 결과입니다.

| Factor | Avg Precision | Avg Recall | 비고 |
| :--- | :--- | :--- | :--- |
| 1 | 0.50 | 1.00 | 소규모 데이터셋에서는 1로도 충분 |
| 2 | 0.50 | 1.00 | **권장 기본값** |
| 5 | 0.50 | 1.00 | 안정적인 Recall 보장 |
| 10 | 0.50 | 1.00 | 복잡한 필터링 대비 |

*실제 대규모 데이터셋(1,000개 이상의 청크)에서는 Factor가 낮을수록 Recall이 급격히 떨어질 수 있으므로, Vault 크기에 따라 점진적으로 늘리는 것을 권장합니다.*

## 4. 적용 방법
`HybridSearchService.search()` 호출 시 `filter_expansion_factor` 인자를 전달합니다.

```python
results = service.search(
    query="OpenAI integration",
    k=5,
    filter_expansion_factor=5  # 후보군을 25개까지 확장하여 필터링
)
```
