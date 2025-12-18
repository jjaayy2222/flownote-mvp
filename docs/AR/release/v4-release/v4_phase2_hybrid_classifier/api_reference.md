# FlowNote v4.0 Phase 2 API Reference

> **작성일**: 2025-12-06
> **버전**: v4.0 Phase 2 - Hybrid Classifier Integration
> **Base URL**: `http://localhost:8000`

---

## 📋 개요

Phase 2에서는 **Hybrid Classifier**가 도입되어 분류 시스템이 고도화되었습니다.
모든 분류 요청은 다음 프로세스를 따릅니다:
1. **Rule Engine**: 규칙 기반의 즉각적이고 결정적인 분류 시도.
2. **AI Fallback**: 규칙 매칭 실패 시 GPT-4o 기반의 문맥 인식 분류 수행.
3. **Keyword Extraction**: 보조적인 태그/키워드 추출.
4. **Conflict Resolution**: PARA 분류와 키워드 간의 불일치 해소.

---

## 🔵 Classification API

### 1. 텍스트 분류

```http
POST /classifier/classify
Content-Type: application/json
```

**Request Body** (변경 없음):
```json
{
  "text": "서버 모니터링 대시보드 구축하기",
  "user_id": "user_001",
  "occupation": "DevOps Engineer",
  "areas": ["Infra", "Monitoring"]
}
```

**Response** (Updated):
```json
{
  "category": "Projects",
  "confidence": 0.95,
  "snapshot_id": "hybrid_170183...",
  "conflict_detected": false,
  "requires_review": false,
  "keyword_tags": ["서버", "모니터링", "대시보드"],
  "reasoning": "Rule 'monitor_dashboard' matched",
  "method": "rule", 
  "user_context_matched": true,
  "log_info": {
    "csv_saved": true,
    "json_saved": true
  }
}
```
* **method**: 분류에 사용된 방식 (`rule` 또는 `ai`)
* **reasoning**: 분류 근거 (Rule 이름 또는 AI의 추론 내용)

### 2. 파일 업로드 분류

```http
POST /classifier/file
Content-Type: multipart/form-data
```

**Response** (Updated):
```json
{
  "category": "Archives",
  "confidence": 0.88,
  "snapshot_id": "hybrid_170183...",
  "keyword_tags": ["재무", "보고서", "2024"],
  "reasoning": "Semantic analysis indicating past records",
  "method": "ai",
  "user_context_matched": false
}
```

---

## 📊 성능 벤치마크 (Phase 2)

| 시나리오 | 처리 방식 | 평균 응답 시간 | 비고 |
|---------|----------|---------------|------|
| **Rule Hit** | Rule Engine | **< 10ms** | 즉각 응답, 비용 0 |
| **AI Fallback** | GPT-4o | **~1.5s** | 네트워크/LLM 지연 발생 |

---

## 🧪 테스트 가이드

### 통합 테스트 실행
```bash
pytest tests/integration/test_hybrid_flow.py -v
```

### 성능 테스트 실행
```bash
python scripts/performance_test.py
```
