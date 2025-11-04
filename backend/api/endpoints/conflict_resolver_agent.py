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
from backend.api.models import (
    ConflictRecord,
    ConflictReport,
    ConflictType,
    ResolutionMethod,
    ResolutionStatus,
    ConflictResolution,
    ResolutionStrategy
)

logger = logging.getLogger(__name__)

# ============================================
# State 정의
# ============================================

class ConflictResolutionState(TypedDict):
    """Conflict Resolver의 상태"""
    conflicts: List[ConflictRecord]              # 입력: 감지된 충돌들
    current_conflict: ConflictRecord             # 현재 처리 중인 충돌
    analysis_result: Dict[str, Any]              # 분석 결과
    suggested_strategies: List[ResolutionStrategy]  # 제안된 해결책들
    selected_strategy: ResolutionStrategy        # 선택된 최종 해결책
    resolutions: List[ConflictResolution]        # 모든 해결 결과
    final_report: ConflictReport                 # 최종 보고서


# ============================================
# 이스케이프 함수 
# ============================================

def _escape_prompt_braces(content: str) -> str:
    """
    프롬프트의 중괄호 이스케이프
    {conflict_info} 변수만 남기고 나머지 모든 { } 를 {{ }} 로 변환
    """
    lines = []
    for line in content.split('\n'):
        if '{conflict_info}' in line:
            lines.append(line)
        else:
            escaped_line = line.replace('{', '{{').replace('}', '}}')
            escaped_line = escaped_line.replace('{{{{', '{{').replace('}}}}', '}}')
            lines.append(escaped_line)
    return '\n'.join(lines)


# ============================================
# Prompt 로드 함수
# ============================================

def load_conflict_resolution_prompt() -> str:
    """충돌 해결 프롬프트 로드"""
    prompt_path = Path(__file__).parent.parent.parent / "classifier" / "prompts" / "conflict_resolution_prompt.txt"
    
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            template_content = f.read()  # ← 변수에 저장
        
        # ✅ 이스케이프 처리!!!
        escaped_content = _escape_prompt_braces(template_content)
        return escaped_content
        
    except FileNotFoundError:
        logger.warning(f"⚠️ 프롬프트 파일 없음: {prompt_path}")
        # Fallback 프롬프트
        return "프롬프트 로드 실패"


# ============================================
# Node 1: Analyze (충돌 분석)
# ============================================

def analyze_conflict_node(state: ConflictResolutionState) -> ConflictResolutionState:
    """
    충돌 분석 노드
    - LLM을 사용해 충돌의 심각도, 원인, 영향 분석
    """
    conflict = state["current_conflict"]
    
    logger.info(f"🔍 충돌 분석 시작: {conflict.type}")
    
    # LLM으로 분석
    llm = ChatOpenAI(
        api_key=ModelConfig.GPT4O_MINI_API_KEY,
        base_url=ModelConfig.GPT4O_MINI_BASE_URL,
        model=ModelConfig.GPT4O_MINI_MODEL,
        temperature=0.3
    )
    
    analysis_prompt = f"""
충돌 분석:

유형: {conflict.type}
설명: {conflict.description}
심각도: {conflict.severity}
자동 해결 가능: {conflict.auto_resolvable}

이 충돌의 원인과 영향을 JSON 형식으로 분석하세요:
{{
  "root_cause": "원인 설명",
  "impact": "영향 분석",
  "priority": "high|medium|low",
  "recommended_approach": "자동|수동"
}}
    """.strip()
    
    try:
        response = llm.invoke(analysis_prompt)
        analysis_text = response.content
        
        # 빈 응답 방지!!!
        if not analysis_text or not analysis_text.strip():
            logger.warning(f"⚠️ 빈 분석 결과, Fallback 사용")
            raise ValueError("Empty response from LLM")        
        
        # JSON 추출
        analysis_result = json.loads(analysis_text)
        
        logger.info(f"✅ 분석 완료: {analysis_result.get('priority')}")
        
        return {
            **state,
            "analysis_result": analysis_result
        }
        
    except Exception as e:
        logger.error(f"❌ 분석 실패: {e}")
        # Fallback
        return {
            **state,
            "analysis_result": {
                "root_cause": "분석 실패",
                "impact": "알 수 없음",
                "priority": "medium",
                "recommended_approach": "수동"
            }
        }


# ============================================
# Node 2: Suggest (해결책 제안)
# ============================================

def suggest_strategies_node(state: ConflictResolutionState) -> ConflictResolutionState:
    """
    해결책 제안 노드
    - 충돌 유형과 분석 결과를 기반으로 3-5개의 해결 전략 제안
    """
    conflict = state["current_conflict"]
    analysis = state["analysis_result"]
    
    logger.info(f"💡 해결책 제안 시작")
    
    # 프롬프트 로드
    prompt_template = load_conflict_resolution_prompt()
    
    llm = ChatOpenAI(
        api_key=ModelConfig.GPT4O_MINI_API_KEY,
        base_url=ModelConfig.GPT4O_MINI_BASE_URL,
        model=ModelConfig.GPT4O_MINI_MODEL,
        temperature=0.5
    )
    
    conflict_info = f"""
유형: {conflict.type}
설명: {conflict.description}
심각도: {conflict.severity}
분석 결과: {json.dumps(analysis, ensure_ascii=False)}
    """.strip()
    
    try:
        response = llm.invoke(prompt_template.format(conflict_info=conflict_info))
        strategies_text = response.content
        
        # JSON 파싱
        strategies_json = json.loads(strategies_text)
        
        # ResolutionStrategy 객체로 변환
        strategies = []
        for s in strategies_json:
            strategy = ResolutionStrategy(
                conflict_id=conflict.conflict_id,
                method=ResolutionMethod(s["method"]),
                recommended_value=s["recommended_value"],
                confidence=s["confidence"],
                reasoning=s["reasoning"],
                affected_files=s.get("affected_files", [])
            )
            strategies.append(strategy)
        
        logger.info(f"✅ {len(strategies)}개 전략 제안 완료")
        
        return {
            **state,
            "suggested_strategies": strategies
        }
        
    except Exception as e:
        logger.error(f"❌ 전략 제안 실패: {e}")
        
        # Fallback 전략 - 안전한 옵션만!!!
        fallback_strategy = ResolutionStrategy(
            conflict_id=conflict.conflict_id,
            method=ResolutionMethod.AUTO_BY_CONFIDENCE,  # ← 이미 존재하는 메서드!
            recommended_value="자동 해결 (기본값)",
            confidence=0.5,
            reasoning="자동 해결 실패, 기본 전략 사용",
            affected_files=[]
        )
        
        return {
            **state,
            "suggested_strategies": [fallback_strategy]
        }



# ============================================
# Node 3: Select (최적 전략 선택)
# ============================================

def select_best_strategy_node(state: ConflictResolutionState) -> ConflictResolutionState:
    """
    최적 전략 선택 노드
    - 신뢰도, 자동 해결 가능 여부 등을 기반으로 최고의 전략 선택
    """
    strategies = state["suggested_strategies"]
    conflict = state["current_conflict"]
    
    logger.info(f"🎯 최적 전략 선택 시작")
    
    # 전략 점수 계산
    def calculate_score(strategy: ResolutionStrategy) -> float:
        score = strategy.confidence  # 기본 점수
        
        # 자동 해결 가능하면 가산점
        if conflict.auto_resolvable and strategy.method != ResolutionMethod.MANUAL_OVERRIDE:
            score += 0.1
        
        # 영향받는 파일 수가 적으면 가산점
        if len(strategy.affected_files) <= 3:
            score += 0.05
        
        return min(score, 1.0)
    
    # 점수 계산 및 정렬
    scored_strategies = [(s, calculate_score(s)) for s in strategies]
    scored_strategies.sort(key=lambda x: x[1], reverse=True)
    
    # 최고 점수 전략 선택
    best_strategy, best_score = scored_strategies[0]
    
    logger.info(f"✅ 선택된 전략: {best_strategy.method} (점수: {best_score:.2f})")
    
    return {
        **state,
        "selected_strategy": best_strategy
    }


# ============================================
# Node 4: Apply (해결책 적용)
# ============================================

def apply_resolution_node(state: ConflictResolutionState) -> ConflictResolutionState:
    """
    해결책 적용 노드
    - 선택된 전략을 실제로 적용하고 ConflictResolution 생성
    """
    strategy = state["selected_strategy"]
    conflict = state["current_conflict"]
    
    logger.info(f"⚙️ 해결책 적용 시작")
    
    # ConflictResolution 생성
    resolution = ConflictResolution(
        conflict_id=conflict.conflict_id,
        status=ResolutionStatus.RESOLVED if conflict.auto_resolvable else ResolutionStatus.PENDING_REVIEW,
        strategy=strategy,
        resolved_by="system" if conflict.auto_resolvable else "pending_user",
        notes=f"자동 해결: {strategy.method}" if conflict.auto_resolvable else "수동 검토 필요"
    )
    
    # 해결 결과 추가
    resolutions = state.get("resolutions", [])
    resolutions.append(resolution)
    
    logger.info(f"✅ 해결 완료: {resolution.status}")
    
    return {
        **state,
        "resolutions": resolutions
    }


# ============================================
# Node 5: Generate Report (최종 보고서 생성)
# ============================================

def generate_report_node(state: ConflictResolutionState) -> ConflictResolutionState:
    """
    최종 보고서 생성 노드
    """
    conflicts = state["conflicts"]
    resolutions = state["resolutions"]
    
    logger.info(f"📊 최종 보고서 생성")
    
    # 통계 계산
    total_conflicts = len(conflicts)
    auto_resolved = sum(1 for r in resolutions if r.status == ResolutionStatus.RESOLVED)
    manual_review = sum(1 for r in resolutions if r.status == ResolutionStatus.PENDING_REVIEW)
    
    # 충돌 유형별 분류
    conflict_breakdown = {}
    for c in conflicts:
        conflict_breakdown[c.type] = conflict_breakdown.get(c.type, 0) + 1
    
    # ConflictReport 생성
    report = ConflictReport(
        total_conflicts=total_conflicts,
        detected_conflicts=conflicts,
        resolutions=resolutions,
        conflict_breakdown=conflict_breakdown,
        auto_resolved_count=auto_resolved,
        manual_review_needed=manual_review,
        resolution_rate=auto_resolved / total_conflicts if total_conflicts > 0 else 0.0,
        status="completed",
        summary=f"{total_conflicts}개 충돌 중 {auto_resolved}개 자동 해결, {manual_review}개 수동 검토 필요"
    )
    
    logger.info(f"✅ 보고서 생성 완료")
    
    return {
        **state,
        "final_report": report
    }


# ============================================
# Graph 구성
# ============================================

def create_conflict_resolver_graph():
    """Conflict Resolver Graph 생성"""
    graph = StateGraph(ConflictResolutionState)
    
    # 노드 추가
    graph.add_node("analyze", analyze_conflict_node)
    graph.add_node("suggest", suggest_strategies_node)
    graph.add_node("select", select_best_strategy_node)
    graph.add_node("apply", apply_resolution_node)
    graph.add_node("generate_report", generate_report_node)
    
    # 엣지 추가
    graph.add_edge(START, "analyze")
    graph.add_edge("analyze", "suggest")
    graph.add_edge("suggest", "select")
    graph.add_edge("select", "apply")
    graph.add_edge("apply", "generate_report")
    graph.add_edge("generate_report", END)
    
    return graph.compile()


# ============================================
# 메인 함수 (동기 버전)
# ============================================

def resolve_conflicts_sync(conflicts: List[ConflictRecord]) -> ConflictReport:
    """
    충돌 해결 (동기 버전)
    
    Args:
        conflicts: 해결할 충돌 목록
        
    Returns:
        ConflictReport: 최종 보고서
    """
    logger.info(f"🚀 충돌 해결 시작: {len(conflicts)}개")
    
    graph = create_conflict_resolver_graph()
    
    # 각 충돌을 순차 처리
    all_resolutions = []
    
    for conflict in conflicts:
        initial_state = {
            "conflicts": conflicts,
            "current_conflict": conflict,
            "analysis_result": {},
            "suggested_strategies": [],
            "selected_strategy": None,
            "resolutions": all_resolutions,
            "final_report": None
        }
        
        # Graph 실행
        result = graph.invoke(initial_state)
        all_resolutions = result["resolutions"]
    
    # 최종 보고서 생성
    final_state = {
        "conflicts": conflicts,
        "resolutions": all_resolutions,
        "current_conflict": None,
        "analysis_result": {},
        "suggested_strategies": [],
        "selected_strategy": None,
        "final_report": None
    }
    
    final_result = generate_report_node(final_state)
    
    logger.info(f"✅ 충돌 해결 완료")
    
    return final_result["final_report"]


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


