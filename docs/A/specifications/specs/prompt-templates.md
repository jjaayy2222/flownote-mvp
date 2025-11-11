# Feature Spec: Prompt Templates

**작성일:** 2025.10.23  
**버전:** 1.0 (MVP)  
**담당:** Jay Lee  
**우선순위:** P0 (MVP 필수)

---

## 1. 개요

### 1.1 목적
FAISS 검색 결과를 사용자가 원하는 형식으로 변환하기 위한 프롬프트 템플릿을 제공한다.

### 1.2 범위
- **MVP:** 3개 기본 템플릿 (요약, Q&A, 키워드 추출)
- **v1.1:** 사용자 정의 템플릿
- **v1.2:** 템플릿 마켓플레이스

---

## 2. 사용자 스토리

### 2.1 As a User
```
AS a FlowNote 사용자
I WANT TO 검색 결과를 다양한 형식으로 변환하고
SO THAT 상황에 맞게 정보를 활용할 수 있다
```

### 2.2 시나리오
```
GIVEN FAISS 검색으로 5개 결과를 얻었을 때
WHEN "요약" 템플릿을 선택하면
THEN GPT-4o-mini가 결과를 요약하고
AND Markdown 형식으로 출력된다
```

---

## 3. 기능 요구사항

### 3.1 템플릿 선택 (MVP)

**템플릿 3종:**

1. **요약 (Summary)**
   - 목적: 검색 결과를 간결하게 요약
   - 출력: 3-5문장

2. **Q&A 생성**
   - 목적: 검색 결과에서 질문-답변 쌍 추출
   - 출력: 5개 Q&A

3. **키워드 추출**
   - 목적: 핵심 키워드 5-10개 추출
   - 출력: 태그 형식

---

### 3.2 프롬프트 구조

**기본 구조:**
```python
TEMPLATE = """
[시스템 역할]
당신은 AI 대화 분석 전문가입니다.

[작업 지시]
다음 검색 결과를 {목적}하세요.

[검색 결과]
{search_results}

[출력 형식]
{output_format}
"""
```

---

### 3.3 템플릿 실행

**입력:**
- 템플릿 ID (summary, qa, keywords)
- 검색 결과 (JSON)

**처리:**
1. 템플릿 로드
2. 검색 결과 삽입
3. GPT-4o-mini 호출
4. 결과 파싱

**출력:**
- Markdown 형식 텍스트

---

## 4. 템플릿 상세

### 4.1 요약 템플릿
```python
SUMMARY_TEMPLATE = """
당신은 AI 대화 분석 전문가입니다.

다음 검색 결과를 3-5문장으로 요약하세요:

{search_results}

요약:
- 핵심 내용만 추출
- 간결하고 명확하게
- Markdown 형식 사용
"""
```

---

### 4.2 Q&A 템플릿
```python
QA_TEMPLATE = """
당신은 AI 대화 분석 전문가입니다.

다음 검색 결과에서 5개의 질문-답변 쌍을 추출하세요:

{search_results}

출력 형식:
## Q1: [질문]
A: [답변]

## Q2: [질문]
A: [답변]

...
"""
```

---

### 4.3 키워드 템플릿
```python
KEYWORDS_TEMPLATE = """
당신은 AI 대화 분석 전문가입니다.

다음 검색 결과에서 핵심 키워드 5-10개를 추출하세요:

{search_results}

출력 형식:
`키워드1`, `키워드2`, `키워드3`, ...
"""
```

---

## 5. UI 설계

### 5.1 Streamlit 컴포넌트
```python
# 템플릿 선택
template_choice = st.selectbox(
    "📝 프롬프트 템플릿",
    options=["요약", "Q&A 생성", "키워드 추출"],
    index=0
)

# 실행 버튼
if st.button("템플릿 적용"):
    result = apply_template(template_choice, search_results)
    st.markdown(result)
    
    # 다운로드 버튼
    st.download_button(
        label="📥 결과 다운로드",
        data=result,
        file_name=f"{template_choice}_{timestamp}.md",
        mime="text/markdown"
    )
```

---

## 6. 데이터 모델

### 6.1 템플릿 메타데이터
```python
TEMPLATES = {
    "summary": {
        "id": "summary",
        "name": "요약",
        "description": "검색 결과를 3-5문장으로 요약",
        "prompt": SUMMARY_TEMPLATE,
        "model": "gpt-4o-mini",
        "max_tokens": 500
    },
    "qa": {
        "id": "qa",
        "name": "Q&A 생성",
        "description": "질문-답변 쌍 5개 추출",
        "prompt": QA_TEMPLATE,
        "model": "gpt-4o-mini",
        "max_tokens": 1000
    },
    "keywords": {
        "id": "keywords",
        "name": "키워드 추출",
        "description": "핵심 키워드 5-10개 추출",
        "prompt": KEYWORDS_TEMPLATE,
        "model": "gpt-4o-mini",
        "max_tokens": 200
    }
}
```

---

## 7. 비기능 요구사항

### 7.1 성능
- 템플릿 실행 시간: 5초 이내
- 캐싱: 동일 입력 재요청 방지

### 7.2 비용
- 예상 토큰 수: 500-1000 토큰/요청
- 월 예상 비용: ~$3 (100회 사용 기준)

---

## 8. 에러 처리

### 8.1 에러 케이스
| 에러 | 원인 | 처리 |
|------|------|------|
| 템플릿 없음 | 잘못된 ID | "템플릿을 찾을 수 없습니다" |
| API 호출 실패 | OpenAI 에러 | "잠시 후 다시 시도하세요" |
| 토큰 초과 | 입력 너무 긺 | "검색 결과를 줄여주세요" |
| 출력 파싱 실패 | 형식 오류 | "결과를 다시 생성합니다" |

---

## 9. 테스트 케이스

### 9.1 템플릿 테스트
```
TC-001: 요약 템플릿
- Input: 5개 검색 결과
- Expected: 3-5문장 요약

TC-002: Q&A 템플릿
- Input: 5개 검색 결과
- Expected: 5개 Q&A 쌍

TC-003: 키워드 템플릿
- Input: 5개 검색 결과
- Expected: 5-10개 키워드
```

---

## 10. 구현 우선순위

### P0 (MVP, 10.26-27)
- [x] 3개 기본 템플릿
- [x] 템플릿 선택 UI
- [x] GPT-4o-mini 연동
- [x] Markdown 다운로드

### P1 (v1.1, 11.9-12)
- [ ] 사용자 정의 템플릿
- [ ] 템플릿 저장/불러오기
- [ ] 템플릿 공유

### P2 (v1.2)
- [ ] 템플릿 마켓플레이스
- [ ] 다국어 템플릿
- [ ] 고급 프롬프트 엔지니어링

---

## 11. 참고사항

### 11.1 관련 Spec
- `faiss-search.md` - 검색 결과 입력
- `markdown-export.md` - 결과 저장

### 11.2 기술 스택
- LangChain: `PromptTemplate`
- OpenAI: `gpt-4o-mini`
- Python: `string.Template` (폴백)

### 11.3 프롬프트 최적화
- Few-shot 예시 추가 (v1.1)
- 체인 프롬프트 (v1.2)
- 온도 조절 (0.3-0.7)

---

**End of Spec**