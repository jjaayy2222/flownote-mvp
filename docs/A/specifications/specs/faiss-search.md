# Feature Spec: FAISS Search

**작성일:** 2025.10.23  
**버전:** 1.0 (MVP)  
**담당:** Jay Lee  
**우선순위:** P0 (MVP 필수)

---

## 1. 개요

### 1.1 목적
업로드된 AI 대화 파일을 FAISS 벡터 DB에 인덱싱하고, 키워드 검색으로 관련 대화를 빠르게 찾을 수 있게 한다.

### 1.2 범위
- **MVP:** 로컬 FAISS 인덱스, 키워드 검색, 유사도 기반 결과 반환
- **v1.1:** Notion 하이브리드 검색
- **v1.2:** 필터링, 정렬, 고급 검색

---

## 2. 사용자 스토리

### 2.1 As a User
```
AS a FlowNote 사용자
I WANT TO 키워드로 AI 대화를 검색하고
SO THAT 관련 내용을 빠르게 찾아볼 수 있다
```

### 2.2 시나리오
```
GIVEN 파일이 업로드되고 인덱싱되었을 때
WHEN "프로젝트 기획" 키워드로 검색하면
THEN 관련도 높은 대화 5개가 표시되고
AND 각 결과에 파일명, 내용 미리보기, 유사도 점수가 포함된다
```

---

## 3. 기능 요구사항

### 3.1 파일 인덱싱 (MVP)

**입력:**
- 업로드된 .md, .txt 파일

**처리:**
1. 파일 내용 읽기 (UTF-8)
2. 텍스트 청킹 (500자 단위, 100자 오버랩)
3. 각 청크를 임베딩 (text-embedding-3-small)
4. FAISS 인덱스에 저장 (data/faiss/)
5. 메타데이터 매핑 (청크 ID ↔ 파일명, 위치)

**출력:**
- 인덱싱 완료 메시지
- 인덱스 크기 표시

---

### 3.2 키워드 검색 (MVP)

**입력:**
- 검색어 (문자열)
- 결과 개수 (기본 5개)

**처리:**
1. 검색어를 임베딩
2. FAISS 유사도 검색 (코사인 유사도)
3. Top-K 결과 추출
4. 메타데이터 조회 (파일명, 위치)
5. 결과 정렬 (유사도 점수 높은 순)

**출력:**
```bash
[
    {
        "chunk_id": 42,
        "filename": "chatgpt_2025-10-23.md",
        "content": "프로젝트 기획 시 고려할 점은...",
        "similarity_score": 0.87,
        "position": "200-700"
    },
    ...
]
```

---

### 3.3 검색 결과 표시

**기능:**
- 검색어 입력 창
- 검색 버튼
- 결과 카드 (파일명, 내용, 점수)
- "전체 보기" 링크 (해당 파일 열기)

---

## 4. 비기능 요구사항

### 4.1 성능
- 인덱싱 속도: 1000자당 1초 이내
- 검색 속도: 1초 이내 (10,000개 청크 기준)

### 4.2 정확도
- Top-5 결과 정확도: 80% 이상
- False Positive 허용: 20% 이하

### 4.3 확장성
- 최대 인덱스 크기: 100MB (MVP)
- 최대 청크 수: 10,000개

---

## 5. UI 설계

### 5.1 Streamlit 컴포넌트
```python
# 검색 입력
search_query = st.text_input(
    "🔍 AI 대화 검색",
    placeholder="예: 프로젝트 기획, Python 코드, ..."
)

# 검색 버튼
if st.button("검색"):
    results = search_faiss(search_query, k=5)
    
    # 결과 표시
    for result in results:
        with st.expander(f"{result['filename']} (유사도: {result['score']:.2f})"):
            st.markdown(result['content'])
            st.button("전체 보기", key=result['chunk_id'])
```

---

## 6. 데이터 모델

### 6.1 FAISS 인덱스 구조
```python
# faiss_index.pkl
{
    "index": faiss.IndexFlatIP,  # Inner Product (코사인 유사도)
    "dimension": 1536,           # text-embedding-3-small
    "total_vectors": 234
}
```

### 6.2 메타데이터 매핑
```python
# metadata.json
{
    "0": {
        "chunk_id": 0,
        "filename": "chatgpt_2025-10-23.md",
        "filepath": "data/uploads/chatgpt_2025-10-23.md",
        "start_pos": 0,
        "end_pos": 500,
        "content": "전체 청크 내용..."
    },
    # ...
}
```

---

## 7. 청킹 전략

### 7.1 청킹 파라미터 (MVP)
```python
CHUNK_SIZE = 500        # 한글 500자 (약 200-250 단어)
CHUNK_OVERLAP = 100     # 100자 오버랩 (문맥 연속성)
```

### 7.2 청킹 로직
```python
from langchain.text_splitter import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""]
)

chunks = splitter.split_text(file_content)
```

---

## 8. 에러 처리

### 8.1 에러 케이스
| 에러 | 원인 | 처리 |
|------|------|------|
| 인덱스 없음 | FAISS 파일 미존재 | "파일을 먼저 업로드하세요" |
| 검색어 비어있음 | 입력 없이 검색 | "검색어를 입력하세요" |
| API 호출 실패 | OpenAI API 에러 | "잠시 후 다시 시도하세요" |
| 인덱스 로딩 실패 | 파일 손상 | "인덱스를 재생성하세요" |

---

## 9. 테스트 케이스

### 9.1 인덱싱 테스트
```markdown
TC-001: 단일 파일 인덱싱
- Input: 1KB .md 파일
- Expected: FAISS 인덱스 생성, 메타데이터 저장

TC-002: 다중 파일 인덱싱
- Input: 3개 .txt 파일
- Expected: 모든 청크가 하나의 인덱스에 병합
```

### 9.2 검색 테스트
```markdown
TC-003: 키워드 검색 (정확한 매칭)
- Input: "프로젝트"
- Expected: "프로젝트" 포함된 청크 상위 5개

TC-004: 유사 의미 검색
- Input: "기획"
- Expected: "계획", "설계" 등 유사 의미 포함 청크

TC-005: 검색 결과 없음
- Input: "존재하지않는키워드"
- Expected: "검색 결과가 없습니다" 메시지
```

---

## 10. 구현 우선순위

### P0 (MVP, 10.24-26)
- [x] 파일 청킹 (500자)
- [x] FAISS 인덱싱 (로컬)
- [x] 키워드 검색 (Top-5)
- [x] 검색 결과 표시

### P1 (v1.1, 11.5-9)
- [ ] Notion 하이브리드 검색
- [ ] 필터링 (파일명, 날짜)
- [ ] 정렬 옵션 (관련도, 날짜)

### P2 (v1.2)
- [ ] 고급 검색 (AND, OR, NOT)
- [ ] 하이라이팅
- [ ] 검색 히스토리

---

## 11. 참고사항

### 11.1 관련 Spec
- `file-upload.md` - 파일 업로드 후 인덱싱
- `prompt-templates.md` - 검색 결과 프롬프트 활용

### 11.2 기술 스택
- FAISS: `faiss-cpu`
- LangChain: `RecursiveCharacterTextSplitter`
- OpenAI: `text-embedding-3-small`
- 저장: `pickle` (인덱스), `json` (메타데이터)

### 11.3 성능 최적화
- 인덱스 로딩: 앱 시작 시 한 번만 (st.cache_resource)
- 검색 캐싱: 동일 쿼리 재검색 방지

---

**End of Spec**