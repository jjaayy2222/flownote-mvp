# Feature Spec: MCP Classification

**작성일:** 2025.10.23  
**버전:** 1.0 (MVP)  
**담당:** Jay Lee  
**우선순위:** P0 (MVP 필수)

---

## 1. 개요

### 1.1 목적
업로드된 AI 대화 파일을 자동으로 분류하여 카테고리별로 정리한다.

### 1.2 범위
- **MVP:** 3개 기본 카테고리 (업무, 학습, 기타), 프롬프트 기반 분류
- **v1.1:** MCP (Model Context Protocol) 활용, 세부 카테고리
- **v1.2:** 사용자 정의 카테고리, 태그 시스템

---

## 2. 사용자 스토리

### 2.1 As a User
```
AS a FlowNote 사용자
I WANT TO 업로드한 파일이 자동으로 분류되고
SO THAT 카테고리별로 쉽게 찾아볼 수 있다
```

### 2.2 시나리오
```
GIVEN 파일을 업로드했을 때
WHEN 파일 내용을 읽어 분석하면
THEN "업무", "학습", "기타" 중 하나로 자동 분류되고
AND 파일 목록에 카테고리 표시된다
```

---

## 3. 기능 요구사항

### 3.1 파일 분류 (MVP)

**카테고리 3종:**

1. **업무 (Work)**
   - 키워드: 프로젝트, 기획, 업무, 회의, 보고서, 제안서, 일정
   - 예시: 프로젝트 기획안, 업무 보고, 회의록

2. **학습 (Learning)**
   - 키워드: 공부, 학습, 코딩, 개발, 튜토리얼, 강의, 공부
   - 예시: Python 튜토리얼, AI 학습, 코드 설명

3. **기타 (Others)**
   - 위 두 카테고리에 해당하지 않는 모든 것
   - 예시: 일상 대화, 창작, 브레인스토밍

---

### 3.2 분류 프롬프트 (MVP)

**프롬프트 구조:**
```
CLASSIFICATION_PROMPT = """
당신은 AI 대화 분류 전문가입니다.

다음 대화 내용을 읽고 가장 적절한 카테고리를 선택하세요:

[대화 내용]
{content}

[카테고리]
1. 업무 (Work): 프로젝트, 기획, 업무, 회의 등
2. 학습 (Learning): 공부, 학습, 코딩, 개발 등
3. 기타 (Others): 위 두 가지에 해당하지 않는 것

[출력 형식]
카테고리: [업무/학습/기타]
이유: [한 문장으로 설명]
"""
```

---

### 3.3 분류 실행

**입력:**
- 파일 경로 (data/uploads/)
- 파일 내용 (첫 1000자)

**처리:**
1. 파일 읽기 (UTF-8)
2. 첫 1000자 추출 (샘플링)
3. 분류 프롬프트에 삽입
4. GPT-4o-mini 호출
5. 응답 파싱 (카테고리 추출)

**출력:**
```
{
    "filename": "chatgpt_2025-10-23.md",
    "category": "업무",
    "reason": "프로젝트 기획 및 일정 논의 포함",
    "confidence": 0.92
}
```

---

## 4. UI 설계

### 4.1 Streamlit 컴포넌트
```
# 파일 목록에 카테고리 추가
import pandas as pd

df = pd.DataFrame(files)
df['카테고리'] = df['filename'].apply(classify_file)

# 카테고리별 필터
category_filter = st.multiselect(
    "📁 카테고리 필터",
    options=["업무", "학습", "기타"],
    default=["업무", "학습", "기타"]
)

# 필터링된 파일 목록 표시
filtered_df = df[df['카테고리'].isin(category_filter)]
st.dataframe(filtered_df)

# 카테고리별 통계
st.metric("업무", len(df[df['카테고리'] == '업무']))
st.metric("학습", len(df[df['카테고리'] == '학습']))
st.metric("기타", len(df[df['카테고리'] == '기타']))
```

---

## 5. 데이터 모델

### 5.1 파일 메타데이터 (업데이트)
```
{
    "filename": "chatgpt_2025-10-23.md",
    "filepath": "data/uploads/chatgpt_2025-10-23.md",
    "uploaded_at": "2025-10-23T14:30:00",
    "size_bytes": 15234,
    "file_type": "markdown",
    "category": "업무",  # 추가!
    "category_reason": "프로젝트 기획 논의",  # 추가!
    "category_confidence": 0.92,  # 추가!
    "status": "uploaded"
}
```

---

## 6. MCP 활용 (v1.1)

### 6.1 MCP란?
- Model Context Protocol
- Anthropic이 개발한 프로토콜
- AI 에이전트가 외부 도구/데이터에 접근하는 표준

### 6.2 MCP 적용 계획
```
# v1.1에서 MCP 활용
from mcp import MCPClient

client = MCPClient()

# 파일 시스템 도구
file_tool = client.get_tool("filesystem")
files = file_tool.list_files("data/uploads/")

# 분류 도구
classifier = client.get_tool("text_classifier")
category = classifier.classify(content, categories=["업무", "학습", "기타"])

# 메타데이터 저장
metadata_tool = client.get_tool("metadata_store")
metadata_tool.save(filename, category)
```

---

## 7. 비기능 요구사항

### 7.1 성능
- 분류 시간: 5초 이내/파일
- 배치 분류: 10개 파일 동시 처리

### 7.2 정확도
- 분류 정확도: 80% 이상 (MVP)
- 신뢰도 임계값: 0.7 (낮으면 "기타"로 분류)

### 7.3 비용
- GPT-4o-mini: ~100 토큰/파일
- 월 예상 비용: ~$1 (100개 파일 기준)

---

## 8. 에러 처리

### 8.1 에러 케이스
| 에러 | 원인 | 처리 |
|------|------|------|
| 파일 읽기 실패 | 인코딩 오류 | "기타"로 분류 |
| API 호출 실패 | OpenAI 에러 | 재시도 3회, 실패 시 "기타" |
| 파싱 실패 | 응답 형식 오류 | "기타"로 분류 |
| 신뢰도 낮음 | confidence < 0.7 | "기타"로 분류 |

---

## 9. 테스트 케이스

### 9.1 분류 테스트
```
TC-001: 업무 파일 분류
- Input: "프로젝트 기획안..."
- Expected: category="업무", confidence>0.8

TC-002: 학습 파일 분류
- Input: "Python 튜토리얼..."
- Expected: category="학습", confidence>0.8

TC-003: 기타 파일 분류
- Input: "오늘 날씨 좋네..."
- Expected: category="기타"
```

### 9.2 예외 테스트
```
TC-004: 애매한 내용
- Input: "어제 회의에서 Python 배웠어"
- Expected: category 결정, confidence 표시

TC-005: 빈 파일
- Input: ""
- Expected: category="기타", reason="내용 없음"
```

---

## 10. 구현 우선순위

### P0 (MVP, 10.28-29)
- [x] 3개 기본 카테고리
- [x] 프롬프트 기반 분류
- [x] GPT-4o-mini 활용
- [x] 카테고리 필터 UI

### P1 (v1.1, 11.14-16)
- [ ] MCP 활용
- [ ] 세부 카테고리 (업무 → 기획, 보고, 회의)
- [ ] 자동 재분류

### P2 (v1.2)
- [ ] 사용자 정의 카테고리
- [ ] 태그 시스템
- [ ] 다중 카테고리 지원

---

## 11. 참고사항

### 11.1 관련 Spec
- `file-upload.md` - 업로드 후 자동 분류
- `faiss-search.md` - 카테고리별 검색

### 11.2 기술 스택
- LangChain: `PromptTemplate`
- OpenAI: `gpt-4o-mini`
- (v1.1) MCP: Anthropic MCP SDK

### 11.3 분류 개선
- Few-shot 예시 추가 (정확도 향상)
- 신뢰도 기반 재확인
- 사용자 피드백 학습 (v1.1)

---

**End of Spec**
