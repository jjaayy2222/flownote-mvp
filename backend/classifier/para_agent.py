# backend/classifier/para_agent.py

"""
LangGraph 기반 PARA Agent (수정 버전)
"""

from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from backend.config import ModelConfig
from backend.classifier.langchain_integration import (
    classify_with_langchain,
    classify_with_metadata
)
import logging

logger = logging.getLogger(__name__)

# 🔷 1. State 정의
class PARAAgentState(TypedDict):
    """Agent 상태 정의"""
    text: str
    metadata: dict
    para_result: dict
    confidence: float
    needs_reanalysis: bool
    final_result: dict

# 🔷 2. Node 함수들
def input_node(state: PARAAgentState) -> PARAAgentState:
    """Input Node - 입력 수집"""
    logger.info(f"Input received: {state['text'][:50]}...")
    return state

def classification_node(state: PARAAgentState) -> PARAAgentState:
    """Classification Node - 텍스트 분류 (정상 경로)"""
    text = state.get("text", "")
    
    # ✅ 텍스트 분류 실행
    try:
        result = classify_with_langchain(text)
        state["para_result"] = result
        logger.info(f"Text classification completed: {result.get('category', 'N/A')}")
    except Exception as e:
        logger.error(f"Classification error: {str(e)}")
        state["para_result"] = {}
    
    return state

def validation_node(state: PARAAgentState) -> PARAAgentState:
    """Validation Node - 텍스트 검증"""
    text = state.get("text", "")
    
    if not text or len(text) < 10:
        state["needs_reanalysis"] = True
        logger.warning("Text too short, needs reanalysis")
    else:
        state["needs_reanalysis"] = False
    
    return state

def reanalysis_node(state: PARAAgentState) -> PARAAgentState:
    """Re-analysis Node - 재분석"""
    if state.get("needs_reanalysis"):
        logger.info("Performing re-analysis...")
        # 메타데이터 활용한 재분석
        try:
            state["para_result"] = classify_with_metadata(state.get("metadata", {}))
        except Exception as e:
            logger.error(f"Re-analysis error: {str(e)}")
            state["para_result"] = {}
    
    return state

def final_decision_node(state: PARAAgentState) -> PARAAgentState:
    """Final Decision Node - 최종 결정"""
    state["final_result"] = state.get("para_result", {})
    logger.info(f"Final result: {state['final_result']}")
    return state

# 🔷 3. Graph 구축
def create_para_agent_graph():
    """PARA Agent Graph 생성"""
    graph = StateGraph(PARAAgentState)
    
    # 노드 추가
    graph.add_node("input", input_node)
    graph.add_node("validation", validation_node)
    graph.add_node("classification", classification_node)  # ✅ 추가!
    graph.add_node("reanalysis", reanalysis_node)
    graph.add_node("final_decision", final_decision_node)
    
    # 엣지 추가
    graph.add_edge(START, "input")
    graph.add_edge("input", "validation")
    
    # ✅ 조건부 분기 수정
    graph.add_conditional_edges(
        "validation",
        lambda x: "reanalysis" if x["needs_reanalysis"] else "classification"
    )
    
    graph.add_edge("classification", "final_decision")  # ✅ 정상 경로
    graph.add_edge("reanalysis", "final_decision")     # ✅ 재분석 경로
    graph.add_edge("final_decision", END)
    
    return graph.compile()

# 🔷 4. 메인 함수
def run_para_agent(text: str, metadata: dict = None) -> dict:
    """PARA Agent 실행"""
    if metadata is None:
        metadata = {}
    
    agent = create_para_agent_graph()
    
    initial_state = {
        "text": text,
        "metadata": metadata,
        "para_result": {},
        "confidence": 0.0,
        "needs_reanalysis": False,
        "final_result": {}
    }
    
    result = agent.invoke(initial_state)
    return result["final_result"]


# 테스트 함수
if __name__ == "__main__":
    # 테스트 1: 정상 경로
    print("Test 1: 정상 경로")
    result1 = run_para_agent(
        text="이번 프로젝트는 새로운 대시보드 기능을 개발하는 것입니다.",
        metadata={}
    )
    print(f"Result: {result1}\n")
    
    # 테스트 2: 재분석 경로
    print("Test 2: 재분석 경로")
    result2 = run_para_agent(
        text="기획",
        metadata={"type": "project"}
    )
    print(f"Result: {result2}")



"""direct_test_result → ⭕️

    python -m backend.classifier.para_agent

    ✅ ModelConfig loaded from backend.config

    Test 1: 정상 경로
    Result: {'category': 'Projects', 'confidence': 0.9, 
            'reasoning': '명확한 목표(새로운 대시보드 기능 개발)와 프로젝트 성격이 드러나므로 Projects로 분류.', 
            'detected_cues': ['프로젝트', '기능 개발'], 'source': 'langchain', 'has_metadata': False}

    Test 2: 재분석 경로
    Text too short, needs reanalysis
    Result: {'category': 'Projects', 'confidence': 0.85, 
            'reasoning': "status가 'in_progress'로 활성 작업을 나타내며, 프로젝트로 분류할 수 있습니다.", 
            'detected_cues': ['status: in_progress'], 'source': 'metadata', 'metadata_used': True}

"""