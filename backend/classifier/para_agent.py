# backend/classifier/para_agent.py

"""
LangGraph 기반 PARA Agent (수정 버전-비동기 ver)
"""

from typing import TypedDict
import asyncio
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
    # 추가
    keyword_result: dict
    conflict_result: dict
    requires_user_review: bool
    

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


def conflict_resolution_node(state: PARAAgentState) -> PARAAgentState:
    """Conflict Resolution Node - 진짜 충돌 해결 로직"""
    
    para_result = state.get("para_result", {})
    keyword_result = state.get("keyword_result", {})
    
    # 테스트 후 딕셔너리 구조로 변환
    conflict_result = {
        "para_decision": para_result.get("category", "Unknown"),
        "para_confidence": para_result.get("confidence", 0.0),
        "keyword_decision": keyword_result.get("category", "None"),
        "is_conflict": para_result.get("category") != keyword_result.get("category"),
        "final_decision": para_result.get("category"),              # PARA 우선
        "reasoning": para_result.get("reasoning", "")
    }
    
    state["conflict_result"] = conflict_result
    state["requires_user_review"] = conflict_result.get("is_conflict", False)
    logger.info(f"✅ Conflict resolved: {conflict_result['final_decision']}")
    
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
    graph.add_node("classification", classification_node)
    graph.add_node("reanalysis", reanalysis_node)
    graph.add_node("conflict_resolution", conflict_resolution_node)
    graph.add_node("final_decision", final_decision_node)
    
    # 엣지 추가
    graph.add_edge(START, "input")
    graph.add_edge("input", "validation")
    
    # 조건부 분기 수정
    graph.add_conditional_edges(
        "validation",
        lambda x: "reanalysis" if x["needs_reanalysis"] else "classification"
    )
    
    # ✅ 새 흐름 (conflict_resolution 포함!)
    graph.add_edge("classification", "conflict_resolution")  # ← 수정!
    graph.add_edge("conflict_resolution", "final_decision")
    graph.add_edge("reanalysis", "final_decision")
    graph.add_edge("final_decision", END)
    
    return graph.compile()

# 🔷 4. 메인 함수 (✅ 비동기 처리!)
async def run_para_agent(text: str, metadata: dict = None) -> dict:
    """PARA Agent 실행 (비동기)"""
    if metadata is None:
        metadata = {}
    
    agent = create_para_agent_graph()
    
    initial_state = {
        "text": text,
        "metadata": metadata,
        "para_result": {},
        "confidence": 0.0,
        "needs_reanalysis": False,
        "final_result": {},
        "keyword_result": {},
        "conflict_result": {},
        "requires_user_review": False,
    }
    
    result = agent.invoke(initial_state)
    return result["final_result"]

# 새로운 동기함수 추가 (동기 wrapper)
def run_para_agent_sync(text: str, metadata: dict = None) -> dict:
    """PARA Agent 실행 (동기) - CLI/API용"""
    if metadata is None:
        metadata = {}
    
    agent = create_para_agent_graph()
    
    initial_state = {
        "text": text,
        "metadata": metadata,
        "para_result": {},
        "confidence": 0.0,
        "needs_reanalysis": False,
        "final_result": {},
        "keyword_result": {},
        "conflict_result": {},
        "requires_user_review": False,
    }
    
    # ✅ 비동기 없음! 직접 실행
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



"""direct_test_result_1 → ⭕️

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


"""direct_test_result_2 → ⭕️

    ➀ 테스트 실행 = `pytest tests/test_para_agent.py::test_para_agent_basic -v`
    
    ============================== test session starts ==============================
    platform darwin -- Python 3.11.10, pytest-8.3.0, pluggy-1.6.0 -- /Users/jay/.pyenv/versions/3.11.10/envs/myenv/bin/python
    cachedir: .pytest_cache
    rootdir: /Users/jay/ICT-projects/flownote-mvp
    plugins: anyio-4.11.0, langsmith-0.4.37
    collected 0 items                                                               

    ============================= no tests ran in 0.68s =============================
    ERROR: not found: /Users/jay/ICT-projects/flownote-mvp/tests/test_para_agent.py::test_para_agent_basic
    (no match in any of [<Module test_para_agent.py>])
    
    ➁ conflict 테스트 = `pytest tests/ -k "conflict" -v 2>&1 | head -60`

    ============================= test session starts ==============================
    platform darwin -- Python 3.11.10, pytest-8.3.0, pluggy-1.6.0 -- /Users/jay/.pyenv/versions/3.11.10/envs/myenv/bin/python
    cachedir: .pytest_cache
    rootdir: /Users/jay/ICT-projects/flownote-mvp
    plugins: anyio-4.11.0, langsmith-0.4.37
    collecting ... collected 33 items / 2 errors / 29 deselected / 4 selected

    ==================================== ERRORS ====================================
    ______________ ERROR collecting tests/test_chunking_embedding.py _______________
    ImportError while importing test module '/Users/jay/ICT-projects/flownote-mvp/tests/test_chunking_embedding.py'.
    Hint: make sure your test modules/packages have valid Python names.
    Traceback:
    ../../.pyenv/versions/3.11.10/lib/python3.11/importlib/__init__.py:126: in import_module
        return _bootstrap._gcd_import(name[level:], package, level)
    tests/test_chunking_embedding.py:16: in <module>
        from backend.chunking import chunk_text, chunk_with_metadata
    E   ImportError: cannot import name 'chunk_text' from 'backend.chunking' (/Users/jay/ICT-projects/flownote-mvp/backend/chunking.py)
    _____________________ ERROR collecting tests/test_faiss.py _____________________
    ImportError while importing test module '/Users/jay/ICT-projects/flownote-mvp/tests/test_faiss.py'.
    Hint: make sure your test modules/packages have valid Python names.
    Traceback:
    ../../.pyenv/versions/3.11.10/lib/python3.11/importlib/__init__.py:126: in import_module
        return _bootstrap._gcd_import(name[level:], package, level)
    tests/test_faiss.py:16: in <module>
        from backend.chunking import chunk_with_metadata
    E   ImportError: cannot import name 'chunk_with_metadata' from 'backend.chunking' (/Users/jay/ICT-projects/flownote-mvp/backend/chunking.py)
    =============================== warnings summary ===============================
    tests/test_compatibility.py:30
    /Users/jay/ICT-projects/flownote-mvp/tests/test_compatibility.py:30: PytestCollectionWarning: cannot collect test class 'TestIntegration' because it has a __init__ constructor (from: tests/test_compatibility.py)
        class TestIntegration:

    -- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
    =========================== short test summary info ============================
    ERROR tests/test_chunking_embedding.py
    ERROR tests/test_faiss.py
    !!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!
    ================= 29 deselected, 1 warning, 2 errors in 6.86s ==================

    - `para_agent.py` 파일 문법 체크 완료
        - conflict_resolution_node 추가
        - State에 3개 필드 추가
        - graph에 node + edge 추가
        - initial_state에 필드 추가
    - 수정 잘 되었음
    - ❌ 테스트 없는 것 (`test_para_agent_basic ()`)

"""



