from typing import TypedDict, List, Optional, NotRequired


class ClassificationResult(TypedDict):
    """분류 결과 데이터 구조"""

    category: str
    confidence: float


class AgentState(TypedDict):
    """
    에이전트가 처리 과정 전반에 걸쳐 공유하는 상태(State) 데이터 구조

    Attributes:
        file_content: 분석할 문서의 원문 내용
        file_name: 분석할 문서의 파일명
        extracted_keywords: InputAnalysis 노드에서 추출한 키워드 리스트
        retrieved_context: ContextRetrieval 노드에서 가져온 맥락 정보 (유사 문서 등)
        retry_count: 재시도 횟수
        classification_result: 최종 분류 결과 (PARA 카테고리 등)
        confidence_score: 분류 신뢰도 (0.0 ~ 1.0)
        reasoning: LLM의 추론 과정 설명
    """

    # 입력 (필수)
    file_content: str
    file_name: str

    # 내부 처리 (선택적)
    extracted_keywords: NotRequired[List[str]]  # 초기값: []
    retrieved_context: NotRequired[Optional[str]]  # 초기값: None
    retry_count: NotRequired[int]  # 초기값: 0

    # 출력 (선택적)
    classification_result: NotRequired[Optional[ClassificationResult]]  # 초기값: None
    confidence_score: NotRequired[float]  # 초기값: 0.0
    reasoning: NotRequired[Optional[str]]  # 초기값: None
