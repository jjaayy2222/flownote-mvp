# backend/api/endpoints/conflict_resolver_agent.py

"""
Conflict Resolution Agent (LangGraph 기반)
- para_agent.py 구조 완벽 재활용
- 충돌 감지 → 분석 → 해결책 제안 → 선택 → 적용
"""

from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from pathlib import Path
import json
import logging

from backend.config import ModelConfig

# 모델 통합 마이그레이션 임포트
from backend.models import (
    ConflictRecord,
    ConflictReport,
    ConflictType,
    ConflictResolution,
    ResolutionMethod,
    ResolutionStatus,
    ResolutionStrategy,
    
)

logger = logging.getLogger(__name__)

# ============================================
# State 정의
# ============================================
class ConflictResolutionState(TypedDict):
    """Conflict Resolver의 상태"""
    conflicts: List[ConflictRecord]  # 입력: 감지된 충돌들
    current_conflict: ConflictRecord  # 현재 처리 중인 충돌
    analysis_result: Dict[str, Any]   # 분석 결과
    suggested_strategies: List[Dict]  # 제안된 전략들
    selected_strategy: Dict           # 선택된 최적 전략
    resolutions: List[ConflictResolution]  # 해결책들
    final_report: ConflictReport      # 최종 보고서


# ============================================
# Node 1: Analyze (충돌 분석)
# ============================================
def analyze_conflict_node(state: ConflictResolutionState) -> ConflictResolutionState:
    """🔍 충돌 분석 노드"""
    conflict = state["current_conflict"]
    logger.info(f"🔍 분석 시작: {conflict.type}")

    llm = ChatOpenAI(
        api_key=ModelConfig.GPT4O_MINI_API_KEY,
        base_url=ModelConfig.GPT4O_MINI_BASE_URL,
        model=ModelConfig.GPT4O_MINI_MODEL,
        temperature=0.0
    )

    analysis_prompt = f"""메타데이터 충돌을 분석하세요.

충돌 정보:
- 유형: {conflict.type}
- 설명: {conflict.description}
- 심각도: {conflict.severity}

JSON만 반환하세요. 마크다운 코드블록 없이!!!

{{"root_cause": "원인", "priority": "high"}}"""

    try:
        response = llm.invoke(analysis_prompt)
        
        # ✅ response 체크
        if not response or not response.content:
            raise ValueError("LLM response is empty")
        
        analysis_text = response.content.strip()
        
        # ✅ 마크다운 제거!!!
        if analysis_text.startswith("```"):
            # 첫 번째 ``` 뒤 제거
            start_idx = analysis_text.find("\n")
            if start_idx != -1:
                analysis_text = analysis_text[start_idx + 1:]
            # 마지막 ```
            end_idx = analysis_text.rfind("```")
            if end_idx != -1:
                analysis_text = analysis_text[:end_idx]
            analysis_text = analysis_text.strip()
        
        if not analysis_text:
            raise ValueError("Empty after cleanup")
        
        logger.info(f"📝 Raw response: {analysis_text[:100]}")
        
        # ✅ JSON 파싱
        try:
            analysis_result = json.loads(analysis_text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 실패: {analysis_text}")
            raise ValueError(f"Invalid JSON: {e}")
        
        logger.info(f"✅ 분석 완료: {analysis_result.get('priority')}")
        
        return {
            **state,
            "analysis_result": analysis_result
        }

    except Exception as e:
        logger.error(f"❌ 분석 실패: {e}")
        return {
            **state,
            "analysis_result": {
                "root_cause": "분석 실패",
                "priority": "medium"
            }
        }


# ============================================
# Node 2: Suggest (해결책 제안)
# ============================================
def suggest_strategies_node(state: ConflictResolutionState) -> ConflictResolutionState:
    """💡 해결책 제안 노드"""
    conflict = state["current_conflict"]
    analysis = state["analysis_result"]
    
    logger.info(f"💡 전략 제안 시작")

    llm = ChatOpenAI(
        api_key=ModelConfig.GPT4O_MINI_API_KEY,
        base_url=ModelConfig.GPT4O_MINI_BASE_URL,
        model=ModelConfig.GPT4O_MINI_MODEL,
        temperature=0.3
    )

    strategy_prompt = f"""충돌 해결 전략을 제안하세요.

분석 결과:
- 원인: {analysis.get("root_cause", "불명")}
- 우선순위: {analysis.get("priority", "medium")}

충돌:
- 유형: {conflict.type}
- 설명: {conflict.description}

JSON만 반환하세요. 마크다운 코드블록 없이!!!

{{"method": "auto_by_confidence", "recommended_value": "값", "confidence": 0.95, "reasoning": "이유"}}"""

    try:
        response = llm.invoke(strategy_prompt)
        
        # ✅ response 체크
        if not response or not response.content:
            raise ValueError("LLM response is empty")
        
        strategy_text = response.content.strip()
        
        # ✅ 마크다운 제거!!!
        if strategy_text.startswith("```"):
            start_idx = strategy_text.find("\n")
            if start_idx != -1:
                strategy_text = strategy_text[start_idx + 1:]
            end_idx = strategy_text.rfind("```")
            if end_idx != -1:
                strategy_text = strategy_text[:end_idx]
            strategy_text = strategy_text.strip()
        
        if not strategy_text:
            raise ValueError("Empty after cleanup")
        
        logger.info(f"📝 Raw response: {strategy_text[:100]}")
        
        # ✅ JSON 파싱
        try:
            strategy = json.loads(strategy_text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 실패: {strategy_text}")
            raise ValueError(f"Invalid JSON: {e}")
        
        logger.info(f"✅ 전략 제안 완료: {strategy.get('method')}")
        
        return {
            **state,
            "suggested_strategies": [strategy]
        }

    except Exception as e:
        logger.error(f"❌ 전략 제안 실패: {e}")
        return {
            **state,
            "suggested_strategies": [{
                "method": ResolutionMethod.MANUAL_OVERRIDE.value,
                "recommended_value": "수동 검토 필요",
                "confidence": 0.3,
                "reasoning": "자동 제안 실패"
            }]
        }


# ============================================
# Node 3: Select (최적 전략 선택)
# ============================================
def select_best_strategy_node(state: ConflictResolutionState) -> ConflictResolutionState:
    """🎯 최적 전략 선택"""
    strategies = state.get("suggested_strategies", [])
    
    if not strategies:
        logger.warning("⚠️  전략 없음")
        return {**state, "selected_strategy": None}
    
    # 신뢰도 기준 정렬
    best = sorted(strategies, key=lambda s: s.get("confidence", 0), reverse=True)[0]
    
    logger.info(f"🎯 선택: {best.get('method')} (신뢰도: {best.get('confidence', 0):.1%})")
    
    return {
        **state,
        "selected_strategy": best
    }


# ============================================
# Node 4: Apply (해결책 적용)
# ============================================
def apply_resolution_node(state: ConflictResolutionState) -> ConflictResolutionState:
    """✅ 해결책 적용"""
    strategy = state.get("selected_strategy")
    conflict = state["current_conflict"]
    
    if not strategy:
        logger.warning("⚠️  적용할 전략 없음")
        return {**state}
    
    # ✅ conflict_id 추가!!!
    strategy["conflict_id"] = conflict.conflict_id
    
    confidence = strategy.get("confidence", 0)
    
    # 신뢰도 기준 판정
    if confidence >= 0.85:
        status = ResolutionStatus.RESOLVED
        resolved_by = "system"
    elif confidence >= 0.5:
        status = ResolutionStatus.PENDING_REVIEW
        resolved_by = "pending_user"
    else:
        status = ResolutionStatus.FAILED
        resolved_by = "manual"
    
    resolution = ConflictResolution(
        conflict_id=conflict.conflict_id,
        status=status,
        strategy=strategy,
        resolved_by=resolved_by,
        notes=f"방법: {strategy.get('method')}, 신뢰도: {confidence:.1%}"
    )
    
    resolutions = state.get("resolutions", [])
    resolutions.append(resolution)
    
    logger.info(f"✅ 해결 적용: {status.value}")
    
    return {
        **state,
        "resolutions": resolutions
    }


# ============================================
# Node 5: Generate Report
# ============================================
def generate_report_node(state: ConflictResolutionState) -> ConflictResolutionState:
    """📊 최종 보고서"""
    conflicts = state.get("conflicts", [])
    resolutions = state.get("resolutions", [])
    
    total = len(conflicts)
    resolved = len([r for r in resolutions 
                    if r.status == ResolutionStatus.RESOLVED])
    pending = len([r for r in resolutions 
                    if r.status == ResolutionStatus.PENDING_REVIEW])
    
    resolution_rate = (resolved / total) if total > 0 else 0.0
    
    report = ConflictReport(
        total_conflicts=total,
        detected_conflicts=conflicts,
        resolutions=resolutions,
        auto_resolved_count=resolved,
        manual_review_needed=pending,
        resolution_rate=resolution_rate,
        status="completed" if resolution_rate >= 0.8 else "partial",
        summary=f"{total}개 중 {resolved}개 자동 해결"
    )
    
    logger.info(f"📊 최종: 해결률 {resolution_rate:.1%}")
    
    return {
        **state,
        "final_report": report
    }


# ============================================
# Graph 구성
# ============================================
def create_conflict_resolver_graph():
    """LangGraph 생성"""
    graph = StateGraph(ConflictResolutionState)
    
    # 노드 추가
    graph.add_node("analyze", analyze_conflict_node)
    graph.add_node("suggest", suggest_strategies_node)
    graph.add_node("select", select_best_strategy_node)
    graph.add_node("apply", apply_resolution_node)
    graph.add_node("report", generate_report_node)
    
    # 엣지 추가
    graph.add_edge(START, "analyze")
    graph.add_edge("analyze", "suggest")
    graph.add_edge("suggest", "select")
    graph.add_edge("select", "apply")
    graph.add_edge("apply", "report")
    graph.add_edge("report", END)
    
    return graph.compile()


# ============================================
# 메인 함수
# ============================================
def resolve_conflicts_sync(conflicts: List[ConflictRecord]) -> ConflictReport:
    """충돌 해결 (동기)"""
    logger.info(f"🚀 시작: {len(conflicts)}개 충돌")
    
    graph = create_conflict_resolver_graph()
    
    all_resolutions = []
    
    # 각 충돌 처리
    for idx, conflict in enumerate(conflicts):
        logger.info(f"[{idx+1}/{len(conflicts)}] 처리 중...")
        
        initial_state = {
            "conflicts": conflicts,
            "current_conflict": conflict,
            "analysis_result": {},
            "suggested_strategies": [],
            "selected_strategy": None,
            "resolutions": all_resolutions,
            "final_report": None
        }
        
        result = graph.invoke(initial_state)
        all_resolutions = result["resolutions"]
    
    # 최종 보고서
    total = len(conflicts)
    resolved = len([r for r in all_resolutions 
                    if r.status == ResolutionStatus.RESOLVED])
    pending = len([r for r in all_resolutions 
                    if r.status == ResolutionStatus.PENDING_REVIEW])
    
    resolution_rate = (resolved / total) if total > 0 else 0.0
    
    final_report = ConflictReport(
        total_conflicts=total,
        detected_conflicts=conflicts,
        resolutions=all_resolutions,
        auto_resolved_count=resolved,
        manual_review_needed=pending,
        resolution_rate=resolution_rate,
        status="completed" if resolution_rate >= 0.8 else "partial",
        summary=f"{total}개 중 {resolved}개 자동 해결, {pending}개 수동 검토 필요"
    )
    
    logger.info(f"✅ 완료!!! 해결률: {resolution_rate:.1%}")
    
    return final_report




# ============================================
# 테스트 함수
# ============================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # 테스트 충돌 생성
    test_conflicts = [
        ConflictRecord(
            type=ConflictType.KEYWORD_CONFLICT,
            description="유사 키워드: 'python' vs 'py'",
            severity=0.8,
            auto_resolvable=True
        ),
        ConflictRecord(
            type=ConflictType.CATEGORY_CONFLICT,
            description="파일 file_001이 여러 카테고리에 속함",
            severity=0.7,
            auto_resolvable=False
        )
    ]
    
    # 해결 실행
    report = resolve_conflicts_sync(test_conflicts)
    
    print("\n" + "="*60)
    print("📊 최종 보고서")
    print("="*60)
    print(f"총 충돌: {report.total_conflicts}")
    print(f"자동 해결: {report.auto_resolved_count}")
    print(f"수동 검토: {report.manual_review_needed}")
    print(f"해결률: {report.resolution_rate:.1%}")
    print(f"\n요약: {report.summary}")
    print("="*60)




"""test_result_1 - 복잡한 프롬프트 

    ```bash
    python -c "
    from backend.api.endpoints.conflict_resolver import ConflictDetector
    from backend.api.endpoints.conflict_resolver_agent import resolve_conflicts_sync

    detector = ConflictDetector(data_source='mock')
    report_detect = detector.detect_all()
    report_resolve = resolve_conflicts_sync(report_detect.detected_conflicts)
    print(f'✅ 해결률: {report_resolve.resolution_rate:.1%}')
    "
    ❌ 분석 실패: Expecting value: line 1 column 1 (char 0)
    ❌ 분석 실패: Expecting value: line 1 column 1 (char 0)
    ✅ 해결률: 100.0%
    ```

"""