# backend/agent/chat/state.py

from typing import Annotated, TypedDict, Any, Optional, NotRequired
from langchain_core.messages import BaseMessage
import operator

# =================================================================
# Type Definitions
# =================================================================


class AgentState(TypedDict):
    """
    채팅 특화 멀티 에이전트를 위한 상태(State) 스키마

    이 상태 객체는 LangGraph 워크플로우를 통과하면서 각 노드별로 업데이트됩니다.
    'messages' 콜렉션은 기존 메시지에 새 메시지를 누적(append)하는 역할을 합니다.

    Attributes:
        messages: 사용자 질문, 도구 호출, LLM 응답 등의 메시지 이력 (누적형)
        user_id: 대화 중인 사용자 ID (개인화 및 Context 기반 응답용)
        session_id: 현재 대화 세션 ID (로깅 및 히스토리 관리용)
        search_context: RAG 등에서 검색해 온 문맥/문서 데이터 문자열
        final_answer: 클라이언트(프론트)로 내보낼 최종 결정된 답변 문자열 (필요 시)
    """

    # 메시지 리스트: 누적 축적을 위해 Annotated와 operator.add를 활용합니다.
    # 이전 배열에 새로운 배열이 들어오면 계속 덧붙여집니다.
    # list[BaseMessage]를 사용해 가변 컬렉션임을 명시적으로 표현합니다.
    messages: Annotated[list[BaseMessage], operator.add]

    # 사용자 식별자 및 세션 정보
    user_id: str
    session_id: NotRequired[Optional[str]]

    # 입력된 정보나 중간 연산 결과물
    search_context: NotRequired[Optional[str]]

    # 플래너 실패 여부 플래그는 search_context에 시스템 메시지가 실리지 않도록 별도 상태로 관리
    planner_failed: NotRequired[Optional[bool]]
    planner_error_message: NotRequired[Optional[str]]

    # 클라이언트에게 반환할 최종 완성 답변
    final_answer: NotRequired[Optional[str]]
