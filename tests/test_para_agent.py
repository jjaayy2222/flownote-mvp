# tests/test_para_agent.py

"""
LangGraph PARA Agent 테스트
4개 노드의 워크플로우 검증
"""

import sys
from pathlib import Path

# 경로 설정
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
from backend.classifier.para_agent import run_para_agent, create_para_agent_graph

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🎯 테스트 데이터
test_cases = [
    {
        "name": "Test 1: 충분한 텍스트 (정상 경로)",
        "text": "이번 프로젝트는 새로운 대시보드 기능을 개발하는 것입니다. 사용자 인터페이스를 개선하고 성능을 최적화하는 것이 목표입니다.",
        "metadata": {
            "author": "jay",
            "date": "2025-11-02",
            "priority": "high"
        },
        "expect_reanalysis": False
    },
    {
        "name": "Test 2: 짧은 텍스트 (재분석 경로)",
        "text": "기획",
        "metadata": {
            "author": "jay",
            "date": "2025-11-02",
            "category": "project",
            "department": "product"
        },
        "expect_reanalysis": True
    },
    {
        "name": "Test 3: 중간 길이 텍스트",
        "text": "다음 분기의 마케팅 전략을 계획해야 합니다",
        "metadata": {
            "author": "marketing_team",
            "date": "2025-11-02"
        },
        "expect_reanalysis": False
    },
    {
        "name": "Test 4: 매우 짧은 텍스트 (재분석 필요)",
        "text": "아",
        "metadata": {
            "author": "jay",
            "date": "2025-11-02",
            "type": "resource"
        },
        "expect_reanalysis": True
    },
    {
        "name": "Test 5: 빈 메타데이터",
        "text": "이 문서는 학습 자료입니다. 파이썬 프로그래밍에 대한 기초 개념을 설명합니다.",
        "metadata": {},
        "expect_reanalysis": False
    }
]

# 🎯 테스트 함수
def test_para_agent_flow():
    """LangGraph Agent 전체 흐름 테스트"""
    print("\n" + "="*70)
    print("🚀 PARA Agent 테스트 시작")
    print("="*70 + "\n")
    
    passed = 0
    failed = 0
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{test_case['name']}")
        print("-" * 70)
        
        try:
            # Agent 실행
            text = test_case['text']
            metadata = test_case['metadata']
            
            print(f"📝 Input Text: {text[:50]}..." if len(text) > 50 else f"📝 Input Text: {text}")
            print(f"📋 Metadata: {metadata}")
            
            # Agent 호출
            result = run_para_agent(text=text, metadata=metadata)
            
            print(f"\n✅ Result:")
            print(f"   - Category: {result.get('category', 'N/A')}")
            print(f"   - Confidence: {result.get('confidence', 'N/A')}")
            
            # 검증
            if result and 'category' in result:
                print(f"✅ TEST PASSED (테스트 #{i})")
                passed += 1
            else:
                print(f"❌ TEST FAILED - 결과가 없음 (테스트 #{i})")
                failed += 1
                
        except Exception as e:
            print(f"❌ TEST FAILED - 에러 발생: {str(e)}")
            logger.error(f"Test {i} error: {str(e)}")
            failed += 1
    
    # 최종 결과
    print("\n" + "="*70)
    print(f"📊 테스트 결과: {passed} 통과, {failed} 실패")
    print("="*70)
    
    return passed, failed

# 🎯 Graph 구조 테스트
def test_graph_structure():
    """Graph 구조 검증"""
    print("\n" + "="*70)
    print("📐 Graph 구조 검증")
    print("="*70 + "\n")
    
    try:
        graph = create_para_agent_graph()
        print("✅ Graph 생성 성공")
        print(f"   - Type: {type(graph)}")
        print(f"✅ Graph 컴파일 완료")
        return True
    except Exception as e:
        print(f"❌ Graph 생성 실패: {str(e)}")
        return False

# 🎯 경로 분석 테스트
def test_path_routing():
    """정상/재분석 경로 분기 테스트"""
    print("\n" + "="*70)
    print("🔀 경로 라우팅 테스트")
    print("="*70 + "\n")
    
    # 정상 경로 테스트
    print("1️⃣ 정상 경로 (텍스트 충분):")
    text_normal = "프로젝트 기획 문서입니다. 매우 상세한 내용이 포함되어 있습니다."
    result_normal = run_para_agent(text=text_normal, metadata={})
    print(f"   ✅ 완료: {result_normal.get('category', 'N/A')}")
    
    # 재분석 경로 테스트
    print("\n2️⃣ 재분석 경로 (텍스트 부족):")
    text_short = "기획"
    result_short = run_para_agent(
        text=text_short,
        metadata={"type": "project", "priority": "high"}
    )
    print(f"   ✅ 완료 (메타데이터 사용): {result_short.get('category', 'N/A')}")

# 🎯 메인 함수
def main():
    """모든 테스트 실행"""
    print("\n🎯 LangGraph PARA Agent 통합 테스트\n")
    
    # 1. Graph 구조 테스트
    structure_ok = test_graph_structure()
    
    # 2. 경로 라우팅 테스트
    if structure_ok:
        test_path_routing()
    
    # 3. 전체 흐름 테스트
    passed, failed = test_para_agent_flow()
    
    # 최종 요약
    print("\n" + "="*70)
    print("📈 최종 요약")
    print("="*70)
    print(f"✅ 총 {passed + failed}개 테스트 중 {passed}개 통과")
    print(f"❌ {failed}개 실패")
    
    if failed == 0:
        print("\n🎉 모든 테스트 통과!!")
    else:
        print(f"\n⚠️ {failed}개 테스트 실패")

if __name__ == "__main__":
    main()
    print("\n🎉 테스트 완료!")



"""test_result_1 → 🔼

    ✅ ModelConfig loaded from backend.config

    🎯 LangGraph PARA Agent 통합 테스트


    ======================================================================
    📐 Graph 구조 검증
    ======================================================================

    ✅ Graph 생성 성공
        - Type: <class 'langgraph.graph.state.CompiledStateGraph'>
    ✅ Graph 컴파일 완료

    ======================================================================
    🔀 경로 라우팅 테스트
    ======================================================================

    1️⃣ 정상 경로 (텍스트 충분):
        INFO:backend.classifier.para_agent:Input received: 프로젝트 기획 문서입니다. 매우 상세한 내용이 포함되어 있습니다....
        INFO:backend.classifier.para_agent:Final result: {}
    ✅ 완료: N/A

    2️⃣ 재분석 경로 (텍스트 부족):
        INFO:backend.classifier.para_agent:Input received: 기획...
        WARNING:backend.classifier.para_agent:Text too short, needs reanalysis
        INFO:backend.classifier.para_agent:Performing re-analysis...
        INFO:httpx:HTTP Request: POST https:*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:메타데이터 분류 완료: Projects (confidence: 95.00%)
        INFO:backend.classifier.para_agent:Final result: 
            {'category': 'Projects', 'confidence': 0.95, 'reasoning': "status가 'in_progress'이고 priority가 'high'로 설정되어 있어 명확한 기한과 목표가 있는 작업으로 판단됨.", 
            'detected_cues': ['status: in_progress', 'priority: high'], 'source': 'metadata', 'metadata_used': True}
    ✅ 완료 (메타데이터 사용): Projects

    ======================================================================
    🚀 PARA Agent 테스트 시작
    ======================================================================


    Test 1: 충분한 텍스트 (정상 경로)
    ----------------------------------------------------------------------
    📝 Input Text: 이번 프로젝트는 새로운 대시보드 기능을 개발하는 것입니다. 사용자 인터페이스를 개선하고 성...
    📋 Metadata: {'author': 'jay', 'date': '2025-11-02', 'priority': 'high'}
        INFO:backend.classifier.para_agent:Input received: 이번 프로젝트는 새로운 대시보드 기능을 개발하는 것입니다. 사용자 인터페이스를 개선하고 성...
        INFO:backend.classifier.para_agent:Final result: {}

    ✅ Result:
        - Category: N/A
        - Confidence: N/A
        ❌ TEST FAILED - 결과가 없음 (테스트 #1)

    Test 2: 짧은 텍스트 (재분석 경로)
    ----------------------------------------------------------------------
    📝 Input Text: 기획
    📋 Metadata: {'author': 'jay', 'date': '2025-11-02', 'category': 'project', 'department': 'product'}
        INFO:backend.classifier.para_agent:Input received: 기획...
        WARNING:backend.classifier.para_agent:Text too short, needs reanalysis
        INFO:backend.classifier.para_agent:Performing re-analysis...
        INFO:httpx:HTTP Request: POST https:*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:메타데이터 분류 완료: Projects (confidence: 90.00%)
        INFO:backend.classifier.para_agent:Final result: 
            {'category': 'Projects', 'confidence': 0.9, 'reasoning': "status가 'project'로 명시되어 있으며, deadline이 존재하지 않지만 프로젝트로 분류할 수 있는 신호가 있습니다.", 
            'detected_cues': ['status: project'], 'source': 'metadata', 'metadata_used': True}

    ✅ Result:
        - Category: Projects
        - Confidence: 0.9
    ✅ TEST PASSED (테스트 #2)

    Test 3: 중간 길이 텍스트
    ----------------------------------------------------------------------
    📝 Input Text: 다음 분기의 마케팅 전략을 계획해야 합니다
    📋 Metadata: {'author': 'marketing_team', 'date': '2025-11-02'}
        INFO:backend.classifier.para_agent:Input received: 다음 분기의 마케팅 전략을 계획해야 합니다...
        INFO:backend.classifier.para_agent:Final result: {}

    ✅ Result:
        - Category: N/A
        - Confidence: N/A
        ❌ TEST FAILED - 결과가 없음 (테스트 #3)

    Test 4: 매우 짧은 텍스트 (재분석 필요)
    ----------------------------------------------------------------------
    📝 Input Text: 아
    📋 Metadata: {'author': 'jay', 'date': '2025-11-02', 'type': 'resource'}
        INFO:backend.classifier.para_agent:Input received: 아...
        WARNING:backend.classifier.para_agent:Text too short, needs reanalysis
        INFO:backend.classifier.para_agent:Performing re-analysis...
        INFO:httpx:HTTP Request: POST https:*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:메타데이터 분류 완료: Resources (confidence: 80.00%)
        INFO:backend.classifier.para_agent:Final result: 
            {'category': 'Resources', 'confidence': 0.8, 
            'reasoning': "제공된 메타데이터는 'type'이 'resource'로 명시되어 있어 참고용 자료로 분류됩니다. 그러나 추가적인 정보가 부족하여 신뢰도를 높일 수 없습니다.", 
            'detected_cues': ['type: resource'], 'source': 'metadata', 'metadata_used': True}

    ✅ Result:
        - Category: Resources
        - Confidence: 0.8
    ✅ TEST PASSED (테스트 #4)

    Test 5: 빈 메타데이터
    ----------------------------------------------------------------------
    📝 Input Text: 이 문서는 학습 자료입니다. 파이썬 프로그래밍에 대한 기초 개념을 설명합니다.
    📋 Metadata: {}
        INFO:backend.classifier.para_agent:Input received: 이 문서는 학습 자료입니다. 파이썬 프로그래밍에 대한 기초 개념을 설명합니다....
        INFO:backend.classifier.para_agent:Final result: {}

    ✅ Result:
        - Category: N/A
        - Confidence: N/A
        ❌ TEST FAILED - 결과가 없음 (테스트 #5)

    ======================================================================
    📊 테스트 결과: 2 통과, 3 실패
    ======================================================================

    ======================================================================
    📈 최종 요약
    ======================================================================
    ✅ 총 5개 테스트 중 2개 통과
    ❌ 3개 실패

    ⚠️ 3개 테스트 실패

    🎉 테스트 완료!

"""


"""test_result_2 → ⭕️

    조건부 분기 수정 
    
    ✅ ModelConfig loaded from backend.config

    🎯 LangGraph PARA Agent 통합 테스트


    ======================================================================
    📐 Graph 구조 검증
    ======================================================================

    ✅ Graph 생성 성공
        - Type: <class 'langgraph.graph.state.CompiledStateGraph'>
    ✅ Graph 컴파일 완료

    ======================================================================
    🔀 경로 라우팅 테스트
    ======================================================================

    1️⃣ 정상 경로 (텍스트 충분):
        INFO:backend.classifier.para_agent:Input received: 프로젝트 기획 문서입니다. 매우 상세한 내용이 포함되어 있습니다....
        INFO:httpx:HTTP Request: POST https://*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:분류 완료: Projects (confidence: 90.00%, metadata: False)
        INFO:backend.classifier.para_agent:Text classification completed: Projects
        INFO:backend.classifier.para_agent:Final result: 
            {'category': 'Projects', 'confidence': 0.9, 
            'reasoning': '프로젝트 기획 문서로서 명확한 목표와 기한이 포함된 작업으로 분류됨. 기획 문서는 일반적으로 특정 목표를 달성하기 위한 계획을 포함하므로 Projects 카테고리에 적합함.', 
            'detected_cues': ['프로젝트', '기획', '상세한 내용'], 'source': 'langchain', 'has_metadata': False}
    ✅ 완료: Projects

    2️⃣ 재분석 경로 (텍스트 부족):
        INFO:backend.classifier.para_agent:Input received: 기획...
        WARNING:backend.classifier.para_agent:Text too short, needs reanalysis
        INFO:backend.classifier.para_agent:Performing re-analysis...
        INFO:httpx:HTTP Request: POST https://*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:메타데이터 분류 완료: Projects (confidence: 95.00%)
        INFO:backend.classifier.para_agent:Final result: 
            {'category': 'Projects', 'confidence': 0.95, 'reasoning': "status가 'in_progress'이고 urgency가 'high'로 설정되어 있어 명확한 기한과 목표가 있는 작업으로 판단됨.", 
            'detected_cues': ['status: in_progress', 'urgency: high'], 'source': 'metadata', 'metadata_used': True}
    ✅ 완료 (메타데이터 사용): Projects

    ======================================================================
    🚀 PARA Agent 테스트 시작
    ======================================================================


    Test 1: 충분한 텍스트 (정상 경로)
    ----------------------------------------------------------------------
    📝 Input Text: 이번 프로젝트는 새로운 대시보드 기능을 개발하는 것입니다. 사용자 인터페이스를 개선하고 성...
    📋 Metadata: {'author': 'jay', 'date': '2025-11-02', 'priority': 'high'}
        INFO:backend.classifier.para_agent:Input received: 이번 프로젝트는 새로운 대시보드 기능을 개발하는 것입니다. 사용자 인터페이스를 개선하고 성...
        INFO:httpx:HTTP Request: POST https://*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:분류 완료: Projects (confidence: 90.00%, metadata: False)
        INFO:backend.classifier.para_agent:Text classification completed: Projects
        INFO:backend.classifier.para_agent:Final result: 
            {'category': 'Projects', 'confidence': 0.9, 
            'reasoning': '구체적인 목표(새로운 대시보드 기능 개발)와 명확한 작업(사용자 인터페이스 개선 및 성능 최적화)이 있어 Projects로 분류됨.', 
            'detected_cues': ['프로젝트', '목표', '개발', '개선', '최적화'], 'source': 'langchain', 'has_metadata': False}

    ✅ Result:
        - Category: Projects
        - Confidence: 0.9
    ✅ TEST PASSED (테스트 #1)

    Test 2: 짧은 텍스트 (재분석 경로)
    ----------------------------------------------------------------------
    📝 Input Text: 기획
    📋 Metadata: {'author': 'jay', 'date': '2025-11-02', 'category': 'project', 'department': 'product'}
        INFO:backend.classifier.para_agent:Input received: 기획...
        WARNING:backend.classifier.para_agent:Text too short, needs reanalysis
        INFO:backend.classifier.para_agent:Performing re-analysis...
        INFO:httpx:HTTP Request: POST https://*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:메타데이터 분류 완료: Projects (confidence: 90.00%)
        INFO:backend.classifier.para_agent:Final result: 
            {'category': 'Projects', 'confidence': 0.9, 
            'reasoning': "status가 'in_progress'로 명시되어 있어 현재 진행 중인 작업으로 판단됨. deadline이 존재하지 않지만, urgency가 'high'로 설정되어 있어 프로젝트로 분류됨.", 
            'detected_cues': ['status: in_progress', 'urgency: high'], 'source': 'metadata', 'metadata_used': True}

    ✅ Result:
        - Category: Projects
        - Confidence: 0.9
    ✅ TEST PASSED (테스트 #2)

    Test 3: 중간 길이 텍스트
    ----------------------------------------------------------------------
    📝 Input Text: 다음 분기의 마케팅 전략을 계획해야 합니다
    📋 Metadata: {'author': 'marketing_team', 'date': '2025-11-02'}
        INFO:backend.classifier.para_agent:Input received: 다음 분기의 마케팅 전략을 계획해야 합니다...
        INFO:httpx:HTTP Request: POST https://*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:분류 완료: Projects (confidence: 90.00%, metadata: False)
        INFO:backend.classifier.para_agent:Text classification completed: Projects
        INFO:backend.classifier.para_agent:Final result: 
            {'category': 'Projects', 'confidence': 0.9, 
            'reasoning': "기한이 명시되지 않았지만 '계획해야 합니다'라는 표현이 있어 특정 목표(마케팅 전략)를 달성하기 위한 작업으로 해석됨. 따라서 Projects로 분류.", 
            'detected_cues': ['계획', '마케팅 전략'], 'source': 'langchain', 'has_metadata': False}

    ✅ Result:
        - Category: Projects
        - Confidence: 0.9
    ✅ TEST PASSED (테스트 #3)

    Test 4: 매우 짧은 텍스트 (재분석 필요)
    ----------------------------------------------------------------------
    📝 Input Text: 아
    📋 Metadata: {'author': 'jay', 'date': '2025-11-02', 'type': 'resource'}
        INFO:backend.classifier.para_agent:Input received: 아...
        WARNING:backend.classifier.para_agent:Text too short, needs reanalysis
        INFO:backend.classifier.para_agent:Performing re-analysis...
        INFO:httpx:HTTP Request: POST https://*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:메타데이터 분류 완료: Resources (confidence: 80.00%)
        INFO:backend.classifier.para_agent:Final result: 
            {'category': 'Resources', 'confidence': 0.8, 
            'reasoning': "제공된 메타데이터는 'resource' 유형으로, 참고용 자료로 분류됩니다. 그러나 추가적인 정보가 부족하여 신뢰도가 낮습니다.", 
            'detected_cues': ['type: resource'], 'source': 'metadata', 'metadata_used': True}

    ✅ Result:
        - Category: Resources
        - Confidence: 0.8
    ✅ TEST PASSED (테스트 #4)

    Test 5: 빈 메타데이터
    ----------------------------------------------------------------------
    📝 Input Text: 이 문서는 학습 자료입니다. 파이썬 프로그래밍에 대한 기초 개념을 설명합니다.
    📋 Metadata: {}
        INFO:backend.classifier.para_agent:Input received: 이 문서는 학습 자료입니다. 파이썬 프로그래밍에 대한 기초 개념을 설명합니다....
        INFO:httpx:HTTP Request: POST https://*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:분류 완료: Resources (confidence: 90.00%, metadata: False)
        INFO:backend.classifier.para_agent:Text classification completed: Resources
        INFO:backend.classifier.para_agent:Final result: 
            {'category': 'Resources', 'confidence': 0.9, 
            'reasoning': "학습 자료로서 파이썬 프로그래밍의 기초 개념을 설명하고 있어 참고용 자료의 성격을 가집니다. '설명'이라는 키워드가 포함되어 있어 Resources로 분류됩니다.", 
            'detected_cues': ['학습 자료', '설명'], 'source': 'langchain', 'has_metadata': False}

    ✅ Result:
        - Category: Resources
        - Confidence: 0.9
    ✅ TEST PASSED (테스트 #5)

    ======================================================================
    📊 테스트 결과: 5 통과, 0 실패
    ======================================================================

    ======================================================================
    📈 최종 요약
    ======================================================================
    ✅ 총 5개 테스트 중 5개 통과
    ❌ 0개 실패

    🎉 모든 테스트 통과!!

    🎉 테스트 완료!

"""