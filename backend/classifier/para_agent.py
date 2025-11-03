# backend/classifier/para_agent.py

from typing import TypedDict
import asyncio
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from backend.config import ModelConfig
from backend.classifier.langchain_integration import (
    classify_with_langchain, 
)
from backend.classifier.keyword_classifier import KeywordClassifier
from backend.classifier.conflict_resolver import (
    ConflictResolver,
    ClassificationResult
)
from backend.classifier.snapshot_manager import SnapshotManager
from datetime import datetime

# 🔷 State 정의
class PARAAgentState(TypedDict):
    text: str
    metadata: dict
    para_result: dict
    keyword_result: dict
    conflict_result: dict
    snapshot_id: str
    final_result: dict

# 🔷 1. PARA 분류 노드 (✅ 수정!)
def para_classification_node(state: PARAAgentState) -> PARAAgentState:
    """PARA 분류 수행"""
    text = state["text"]
    metadata = state.get("metadata", {})
    
    # ✅ metadata가 있으면 같이 보내고, 없으면 text만 보냄
    if metadata:
        result = classify_with_langchain(text, metadata)
    else:
        result = classify_with_langchain(text)
    
    return {
        **state,
        "para_result": result
    }

# 🔷 2. Keyword 분류 노드 (✅ Step 2)
def keyword_classification_node(state: PARAAgentState) -> PARAAgentState:
    """Keyword 분류 수행"""
    text = state["text"]
    
    classifier = KeywordClassifier()
    keyword_result = classifier.classify(text)
    
    return {
        **state,
        "keyword_result": keyword_result
    }

# 🔷 3. 충돌 해결 노드 (✅ Step 3)
def conflict_resolution_node(state: PARAAgentState) -> PARAAgentState:
    """PARA vs Keyword 충돌 해결"""
    para_result = state.get("para_result", {})
    keyword_result = state.get("keyword_result", {})
    
    # ClassificationResult 객체 생성
    para_obj = ClassificationResult(
        category=para_result.get("category", ""),
        confidence=para_result.get("confidence", 0.0),
        source="para",
        reasoning=para_result.get("reasoning", ""),
        tags=None
    )
    
    keyword_obj = ClassificationResult(
        category=keyword_result.get("tags", [""])[0] if keyword_result.get("tags") else "",
        confidence=keyword_result.get("confidence", 0.0),
        source="keyword",
        reasoning=keyword_result.get("reasoning", ""),
        tags=keyword_result.get("tags", [])
    )
    
    # 충돌 해결
    resolver = ConflictResolver()
    conflict_result = resolver.resolve(para_obj, keyword_obj)
    
    return {
        **state,
        "conflict_result": conflict_result
    }

# 🔷 4. 스냅샷 저장 노드 (✅ 수정!)
def snapshot_node(state: PARAAgentState) -> PARAAgentState:
    """스냅샷 저장"""
    snapshot_mgr = SnapshotManager()
    
    # ✅ metadata 파라미터 제거!
    snapshot_id = snapshot_mgr.save_snapshot(
        text=state["text"],
        para_result=state["para_result"],
        keyword_result=state.get("keyword_result", {}),
        conflict_result=state["conflict_result"]
    )
    
    return {
        **state,
        "snapshot_id": snapshot_id
    }

# 🔷 5. 최종 결정 노드
def final_decision_node(state: PARAAgentState) -> PARAAgentState:
    """최종 결정"""
    conflict_result = state.get("conflict_result", {})
    
    final_result = {
        "category": conflict_result.get("final_category"),
        "confidence": conflict_result.get("confidence"),
        "snapshot_id": state.get("snapshot_id"),
        "conflict_detected": conflict_result.get("conflict_detected", False),
        "requires_review": conflict_result.get("requires_review", False),
        "keyword_tags": conflict_result.get("keyword_tags", []),
        "reasoning": conflict_result.get("reason", "")
    }
    
    return {
        **state,
        "final_result": final_result
    }

# 🔷 6. Graph 생성
def create_para_agent_graph():
    """PARAAgent Graph 생성"""
    graph = StateGraph(PARAAgentState)
    
    # 노드 추가
    graph.add_node("para_classification", para_classification_node)
    graph.add_node("keyword_classification", keyword_classification_node)  # ✅ 추가
    graph.add_node("conflict_resolution", conflict_resolution_node)
    graph.add_node("snapshot", snapshot_node)
    graph.add_node("final_decision", final_decision_node)
    
    # 엣지 추가
    graph.add_edge(START, "para_classification")
    graph.add_edge("para_classification", "keyword_classification")  # ✅ 추가
    graph.add_edge("keyword_classification", "conflict_resolution")  # ✅ 수정
    graph.add_edge("conflict_resolution", "snapshot")
    graph.add_edge("snapshot", "final_decision")
    graph.add_edge("final_decision", END)
    
    return graph.compile()

# 🔷 7. 메인 함수 (비동기)
async def run_para_agent(text: str, metadata: dict = None) -> dict:
    """PARA Agent 실행 (비동기)"""
    if metadata is None:
        metadata = {}
    
    agent = create_para_agent_graph()
    
    initial_state = {
        "text": text,
        "metadata": metadata,
        "para_result": {},
        "keyword_result": {},  # ✅ 추가
        "conflict_result": {},
        "snapshot_id": "",
        "final_result": {}
    }
    
    result = await agent.ainvoke(initial_state)
    return result["final_result"]


# 🔷 8. 동기 래퍼 함수 (✅ 추가!)
def run_para_agent_sync(text: str, metadata: dict = None) -> dict:
    """PARA Agent 실행 (동기 버전 - asyncio.run 래퍼)"""
    return asyncio.run(run_para_agent(text, metadata))



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


"""통합 후 test_result → ⭕️ (테스트 파일: `../tests/test_classify_cli.py`)

    `python tests/test_classify_cli.py`
    
    ✅ ModelConfig loaded from backend.config
    
    🔍 분류 중: '프로젝트 문서 작성'

    ================================================================================
    🔍 원본 LLM 응답:
    ================================================================================
    {
        "tags": ["업무"],
        "confidence": 0.70,
        "matched_keywords": {
            "업무": ["프로젝트"]
        },
        "reasoning": "프로젝트 문서 작성은 업무 관련 활동으로 명확히 분류됨",
        "para_hints": {
            "업무": ["Projects"]
        }
    }
    ================================================================================

    📄 추출된 JSON:
    {
        "tags": ["업무"],
        "confidence": 0.70,
        "matched_keywords": {
            "업무": ["프로젝트"]
        },
        "reasoning": "프로젝트 문서 작성은 업무 관련 활동으로 명확히 분류됨",
        "para_hints": {
            "업무": ["Projects"]
        }
    }


    ✅ 결과:
    Snapshot ID: snap_20251103_194643
    PARA Result: 
        {'category': 'Projects', 'confidence': 0.9, 
        'snapshot_id': Snapshot(id='snap_20251103_194649', 
        timestamp=datetime.datetime(2025, 11, 3, 19, 46, 49, 8536), 
        text='프로젝트 문서 작성', 
        para_result={'category': 'Projects', 'confidence': 0.9, 'reasoning': '프로젝트 문서 작성은 명확한 작업 목표가 있으며, 특정 기한이 암시될 수 있는 작업으로 보아 Projects로 분류됨.', 
                    'detected_cues': ['프로젝트', '문서', '작성'], 'source': 'langchain', 'has_metadata': False}, 
        keyword_result={'tags': ['업무'], 'confidence': 0.7, 
                        'matched_keywords': {'업무': ['프로젝트']}, 
                        'reasoning': '프로젝트 문서 작성은 업무 관련 활동으로 명확히 분류됨', 
                        'para_hints': {'업무': ['Projects']}}, 
        conflict_result={'final_category': 'Projects', 'para_category': 'Projects', 
                        'keyword_tags': ['업무'], 'confidence': 0.9, 'confidence_gap': 0.2, 
                        'conflict_detected': False, 'resolution_method': 'auto_by_confidence', 
                        'requires_review': False, 'winner_source': 'para', 
                        'para_reasoning': '프로젝트 문서 작성은 명확한 작업 목표가 있으며, 특정 기한이 암시될 수 있는 작업으로 보아 Projects로 분류됨.', 
                        'reason': '명확한 승자 선택됨 (Gap: 0.20)'}, 
                        metadata={'confidence': 0, 'is_conflict': False, 'final_category': 'Projects'}), 
        'conflict_detected': False, 'requires_review': False, 'keyword_tags': ['업무'], 'reasoning': '명확한 승자 선택됨 (Gap: 0.20)'
        }
    Conflict Result: {'is_conflict': False}

    📊 저장된 스냅샷:
    총 1개

"""