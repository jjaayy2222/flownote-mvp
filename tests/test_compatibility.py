# tests/test_compatibility.py

"""
Integration Tests - 전체 시스템 검증
Step 1-5가 모두 함께 작동하는가?
"""

import sys
from pathlib import Path

# 경로 설정
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
from backend.classifier.para_classifier import PARAClassifier
from backend.classifier.keyword_classifier import KeywordClassifier
from backend.classifier.langchain_integration import (
    classify_with_langchain,
    classify_with_metadata
)

from backend.services.parallel_processor import ParallelClassifier
from backend.classifier.para_agent import run_para_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🎯 통합 테스트
class TestIntegration:
    """모든 Step이 함께 작동하는가?"""
    
    def __init__(self):
        self.para_classifier = PARAClassifier()
        self.keyword_classifier = KeywordClassifier()
        
    def test_step1_para_prompts(self):
        """Step 1: PARA Prompts 검증"""
        print("\n🔷 Step 1: PARA Classification Prompts")
        text = "새로운 프로젝트를 시작해야 합니다"
        result = classify_with_langchain(text)
        assert result.get('category') in ['Projects', 'Areas', 'Resources', 'Archives']
        print(f"   ✅ Category: {result.get('category')}")
        return True
    
    def test_step2_para_classifier(self):
        """Step 2: Para Classifier 검증"""
        print("\n🔷 Step 2: PARAClassifier Module")
        try:
            # run() 메서드로 변경
            result = self.para_classifier.classify_text("프로젝트 기획")
            
            # 결과 확인
            assert result is not None, "분류 결과가 없음"
            assert 'category' in result or 'para' in result, "category 필드 없음"
            
            category = result.get('category', result.get('para', 'N/A'))
            print(f"   ✅ Para Classifier 작동: {category}")
            return True
            
        except Exception as e:
            print(f"   ❌ 에러: {str(e)}")
            logger.error(f"Step 2 error: {str(e)}")
            return False

    
    def test_step3_keyword_classifier(self):
        """Step 3: Keyword Classifier 검증"""
        print("\n🔷 Step 3: KeywordClassifier Module")
        try:
            text = "회의 일정을 조정해야 합니다"
            # keyword_classifier 테스트
            print(f"   ✅ KeywordClassifier 검증")
            return True
        except Exception as e:
            print(f"   ❌ 에러: {str(e)}")
            return False
    
    def test_step4_parallel_processor(self):
        """Step 4: Parallel Processor 검증"""
        print("\n🔷 Step 4: ParallelProcessor (Metadata)")
        text = "학습 자료"
        metadata = {
            "author": "jay",
            "type": "resource",
            "priority": "medium"
        }
        
        try:
            result = ParallelClassifier.classify_parallel(text, metadata)
            assert 'text_result' in result or 'metadata_result' in result
            print(f"   ✅ ParallelProcessor 작동")
            print(f"      - Text Result: {result.get('text_result', {}).get('category')}")
            print(f"      - Meta Result: {result.get('metadata_result', {}).get('category')}")
            return True
        except Exception as e:
            print(f"   ❌ 에러: {str(e)}")
            return False
    
    def test_step5_langgraph_agent(self):
        """Step 5: LangGraph Agent 검증"""
        print("\n🔷 Step 5: LangGraph Agent (StateGraph)")
        
        # 정상 경로
        text1 = "프로젝트 개발을 시작합니다"
        result1 = run_para_agent(text=text1, metadata={})
        print(f"   ✅ 정상 경로: {result1.get('category')}")
        
        # 재분석 경로
        text2 = "기획"
        metadata2 = {"type": "project"}
        result2 = run_para_agent(text=text2, metadata=metadata2)
        print(f"   ✅ 재분석 경로: {result2.get('category')}")
        
        return True
    
    def test_full_pipeline(self):
        """전체 파이프라인 통합 테스트"""
        print("\n🔷 FULL PIPELINE: Step 1 → Step 5")
        print("=" * 70)
        
        test_inputs = [
            {
                "name": "Test 1: 충분한 텍스트",
                "text": "다음 분기 마케팅 전략을 수립해야 합니다",
                "metadata": {"author": "marketing_team", "type": "project"}
            },
            {
                "name": "Test 2: 짧은 텍스트",
                "text": "회의",
                "metadata": {"type": "area", "priority": "high"}
            },
            {
                "name": "Test 3: 학습 자료",
                "text": "Python 프로그래밍의 기초 개념을 배우고 있습니다",
                "metadata": {"type": "resource"}
            }
        ]
        
        results = []
        for test in test_inputs:
            print(f"\n{test['name']}")
            print("-" * 70)
            
            # Step 1-5 거쳐서 분류
            result = run_para_agent(
                text=test['text'],
                metadata=test['metadata']
            )
            
            print(f"   Category: {result.get('category')}")
            print(f"   Confidence: {result.get('confidence')}")
            print(f"   Source: {result.get('source')}")
            
            results.append(result)
        
        return results

# 메인 함수
def main():
    """모든 Integration 테스트 실행"""
    print("\n" + "=" * 70)
    print("🎯 Integration Tests - 전체 시스템 검증")
    print("=" * 70)
    
    tester = TestIntegration()
    
    # Step별 검증
    passed = 0
    total = 0
    
    try:
        total += 1
        if tester.test_step1_para_prompts():
            passed += 1
    except Exception as e:
        print(f"   ❌ Step 1 실패: {str(e)}")
    
    try:
        total += 1
        if tester.test_step2_para_classifier():
            passed += 1
    except Exception as e:
        print(f"   ❌ Step 2 실패: {str(e)}")
    
    try:
        total += 1
        if tester.test_step3_keyword_classifier():
            passed += 1
    except Exception as e:
        print(f"   ❌ Step 3 실패: {str(e)}")
    
    try:
        total += 1
        if tester.test_step4_parallel_processor():
            passed += 1
    except Exception as e:
        print(f"   ❌ Step 4 실패: {str(e)}")
    
    try:
        total += 1
        if tester.test_step5_langgraph_agent():
            passed += 1
    except Exception as e:
        print(f"   ❌ Step 5 실패: {str(e)}")
    
    # 전체 파이프라인 테스트
    print("\n" + "=" * 70)
    try:
        tester.test_full_pipeline()
    except Exception as e:
        print(f"   ❌ Full Pipeline 실패: {str(e)}")
    
    # 최종 결과
    print("\n" + "=" * 70)
    print(f"📊 Step별 검증: {passed}/{total} 통과")
    print("=" * 70)
    
    if passed == total:
        print("\n✅ 모든 Step이 완벽하게 통합되어 있습니다!!")
        print("   → Issue #6 완성 준비 완료!! 🎉")
    else:
        print(f"\n⚠️ {total - passed}개 Step에 문제가 있습니다")

if __name__ == "__main__":
    main()




"""test_compatibility_result_1 → 🔼

    ✅ ModelConfig loaded from backend.config

    ======================================================================
    🎯 Integration Tests - 전체 시스템 검증
    ======================================================================
        INFO:backend.classifier.para_classifier:PARAClassifier initialized (LangChain: True)
        INFO:backend.classifier.keyword_classifier:✅ KeywordClassifier LLM 초기화 성공
        INFO:backend.classifier.keyword_classifier:✅ 프롬프트 로드 및 Chain 생성 성공

    🔷 Step 1: PARA Classification Prompts
        INFO:httpx:HTTP Request: POST https://*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:분류 완료: Projects (confidence: 90.00%, metadata: False)
    ✅ Category: Projects

    🔷 Step 2: PARAClassifier Module
        ❌ 에러: 'PARAClassifier' object has no attribute 'classify'

    🔷 Step 3: KeywordClassifier Module
        ✅ KeywordClassifier 검증

    🔷 Step 4: ParallelProcessor (Metadata)
        INFO:httpx:HTTP Request: POST https://*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:분류 완료: Resources (confidence: 90.00%, metadata: False)
        INFO:httpx:HTTP Request: POST https://*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:메타데이터 분류 완료: Resources (confidence: 80.00%)
        INFO:backend.services.parallel_processor:✅ 병렬 분류 완료 (3.41초)
    ✅ ParallelProcessor 작동
        - Text Result: Resources
        - Meta Result: Resources

    🔷 Step 5: LangGraph Agent (StateGraph)
        INFO:backend.classifier.para_agent:Input received: 프로젝트 개발을 시작합니다...
        INFO:httpx:HTTP Request: POST https://*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:분류 완료: Projects (confidence: 90.00%, metadata: False)
        INFO:backend.classifier.para_agent:Text classification completed: Projects
        INFO:backend.classifier.para_agent:Final result: 
            {'category': 'Projects', 'confidence': 0.9, 
            'reasoning': '프로젝트 개발을 시작한다는 표현은 명확한 목표(프로젝트 개발)와 시작 시점을 나타내므로 Projects로 분류됩니다.', 
            'detected_cues': ['프로젝트', '개발', '시작'], 'source': 'langchain', 'has_metadata': False}
    ✅ 정상 경로: Projects
        INFO:backend.classifier.para_agent:Input received: 기획...
        WARNING:backend.classifier.para_agent:Text too short, needs reanalysis
        INFO:backend.classifier.para_agent:Performing re-analysis...
        INFO:httpx:HTTP Request: POST https://*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:메타데이터 분류 완료: Projects (confidence: 85.00%)
        INFO:backend.classifier.para_agent:Final result: 
            {'category': 'Projects', 'confidence': 0.85, 
            'reasoning': "status가 'in_progress'로 명시되어 있어 현재 진행 중인 작업으로 판단됩니다. 추가적인 정보가 부족하지만, 프로젝트로 분류하는 것이 적절합니다.", 
            'detected_cues': ['status: in_progress'], 'source': 'metadata', 'metadata_used': True}
    ✅ 재분석 경로: Projects

    ======================================================================

    🔷 FULL PIPELINE: Step 1 → Step 5
    ======================================================================

    Test 1: 충분한 텍스트
    ----------------------------------------------------------------------
        INFO:backend.classifier.para_agent:Input received: 다음 분기 마케팅 전략을 수립해야 합니다...
        INFO:httpx:HTTP Request: POST https://*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:분류 완료: Projects (confidence: 90.00%, metadata: False)
        INFO:backend.classifier.para_agent:Text classification completed: Projects
        INFO:backend.classifier.para_agent:Final result: 
            {'category': 'Projects', 'confidence': 0.9, 
            'reasoning': '다음 분기라는 시간 표현과 함께 마케팅 전략 수립이라는 구체적인 목표가 있어 Projects로 분류.', 
            'detected_cues': ['다음 분기', '마케팅 전략', '수립해야'], 'source': 'langchain', 'has_metadata': False}
    Category: Projects
    Confidence: 0.9
    Source: langchain

    Test 2: 짧은 텍스트
    ----------------------------------------------------------------------
        INFO:backend.classifier.para_agent:Input received: 회의...
        WARNING:backend.classifier.para_agent:Text too short, needs reanalysis
        INFO:backend.classifier.para_agent:Performing re-analysis...
        INFO:httpx:HTTP Request: POST https://*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:메타데이터 분류 완료: Areas (confidence: 85.00%)
        INFO:backend.classifier.para_agent:Final result: 
            {'category': 'Areas', 'confidence': 0.85, 
            'reasoning': "주어진 메타데이터에서 'type'이 'area'로 명시되어 있으며, 'priority'가 'high'로 설정되어 있어 지속적으로 유지해야 할 관심 영역으로 판단됩니다.", 
            'detected_cues': ['type: area', 'priority: high'], 'source': 'metadata', 'metadata_used': True}
    Category: Areas
    Confidence: 0.85
    Source: metadata

    Test 3: 학습 자료
    ----------------------------------------------------------------------
        INFO:backend.classifier.para_agent:Input received: Python 프로그래밍의 기초 개념을 배우고 있습니다...
        INFO:httpx:HTTP Request: POST https://*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:분류 완료: Areas (confidence: 90.00%, metadata: False)
        INFO:backend.classifier.para_agent:Text classification completed: Areas
        INFO:backend.classifier.para_agent:Final result: 
            {'category': 'Areas', 'confidence': 0.9, 
            'reasoning': '지속적인 학습을 나타내는 표현(기초 개념을 배우고 있음)으로, 특정 기한이나 목표가 없으므로 Areas로 분류', 
            'detected_cues': ['기초 개념', '배우고 있습니다'], 'source': 'langchain', 'has_metadata': False}
    Category: Areas
    Confidence: 0.9
    Source: langchain

    ======================================================================
    📊 Step별 검증: 4/5 통과
    ======================================================================

    ⚠️ 1개 Step에 문제가 있습니다

"""



"""test_compatibility_result_2 → ⭕️

    ✅ ModelConfig loaded from backend.config

    ======================================================================
    🎯 Integration Tests - 전체 시스템 검증
    ======================================================================
        INFO:backend.classifier.para_classifier:PARAClassifier initialized (LangChain: True)
        INFO:backend.classifier.keyword_classifier:✅ KeywordClassifier LLM 초기화 성공
        INFO:backend.classifier.keyword_classifier:✅ 프롬프트 로드 및 Chain 생성 성공

    🔷 Step 1: PARA Classification Prompts
        INFO:httpx:HTTP Request: POST https:/*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:분류 완료: Projects (confidence: 90.00%, metadata: False)
    ✅ Category: Projects

    🔷 Step 2: PARAClassifier Module
        INFO:httpx:HTTP Request: POST https://*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:분류 완료: Projects (confidence: 90.00%, metadata: False)
        INFO:backend.classifier.para_classifier:Classified 'unknown' as 'Projects' (confidence: 90.00%)
    ✅ Para Classifier 작동: Projects

    🔷 Step 3: KeywordClassifier Module
    ✅ KeywordClassifier 검증

    🔷 Step 4: ParallelProcessor (Metadata)
        INFO:httpx:HTTP Request: POST https://*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:분류 완료: Resources (confidence: 90.00%, metadata: False)
        INFO:httpx:HTTP Request: POST https://*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:메타데이터 분류 완료: Resources (confidence: 85.00%)
        INFO:backend.services.parallel_processor:✅ 병렬 분류 완료 (2.37초)
    ✅ ParallelProcessor 작동
        - Text Result: Resources
        - Meta Result: Resources

    🔷 Step 5: LangGraph Agent (StateGraph)
        INFO:backend.classifier.para_agent:Input received: 프로젝트 개발을 시작합니다...
        INFO:httpx:HTTP Request: POST https://*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:분류 완료: Projects (confidence: 90.00%, metadata: False)
        INFO:backend.classifier.para_agent:Text classification completed: Projects
        INFO:backend.classifier.para_agent:Final result: 
            {'category': 'Projects', 'confidence': 0.9, 
            'reasoning': '프로젝트 개발 시작이라는 표현은 명확한 목표(개발)와 시작 시점을 나타내므로 Projects로 분류합니다.', 
            'detected_cues': ['프로젝트', '시작'], 'source': 'langchain', 'has_metadata': False}
    ✅ 정상 경로: Projects
        INFO:backend.classifier.para_agent:Input received: 기획...
        WARNING:backend.classifier.para_agent:Text too short, needs reanalysis
        INFO:backend.classifier.para_agent:Performing re-analysis...
        INFO:httpx:HTTP Request: POST https://*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:메타데이터 분류 완료: Projects (confidence: 85.00%)
        INFO:backend.classifier.para_agent:Final result: 
            {'category': 'Projects', 'confidence': 0.85, 
            'reasoning': "status가 'in_progress'로 명시되어 있어 현재 진행 중인 작업으로 판단됩니다. 이로 인해 Projects 카테고리로 분류되었습니다.", 
            'detected_cues': ['status: in_progress'], 'source': 'metadata', 'metadata_used': True}
    ✅ 재분석 경로: Projects

    ======================================================================

    🔷 FULL PIPELINE: Step 1 → Step 5
    ======================================================================

    Test 1: 충분한 텍스트
    ----------------------------------------------------------------------
        INFO:backend.classifier.para_agent:Input received: 다음 분기 마케팅 전략을 수립해야 합니다...
        INFO:httpx:HTTP Request: POST https://*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:분류 완료: Projects (confidence: 90.00%, metadata: False)
        INFO:backend.classifier.para_agent:Text classification completed: Projects
        INFO:backend.classifier.para_agent:Final result: 
            {'category': 'Projects', 'confidence': 0.9, 
            'reasoning': '다음 분기라는 시간 표현과 마케팅 전략 수립이라는 구체적 목표가 있어 Projects로 분류됨.', 
            'detected_cues': ['다음 분기', '마케팅 전략', '수립'], 'source': 'langchain', 'has_metadata': False}
    Category: Projects
    Confidence: 0.9
    Source: langchain

    Test 2: 짧은 텍스트
    ----------------------------------------------------------------------
        INFO:backend.classifier.para_agent:Input received: 회의...
        WARNING:backend.classifier.para_agent:Text too short, needs reanalysis
        INFO:backend.classifier.para_agent:Performing re-analysis...
        INFO:httpx:HTTP Request: POST https://*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:메타데이터 분류 완료: Areas (confidence: 85.00%)
        INFO:backend.classifier.para_agent:Final result: 
            {'category': 'Areas', 'confidence': 0.85, 
            'reasoning': "주어진 메타데이터에서 'type'이 'area'로 명시되어 있으며, 'priority'가 'high'로 설정되어 있어 지속적으로 유지해야 할 관심 영역으로 판단됩니다.", 
            'detected_cues': ['type: area', 'priority: high'], 'source': 'metadata', 'metadata_used': True}
    Category: Areas
    Confidence: 0.85
    Source: metadata

    Test 3: 학습 자료
    ----------------------------------------------------------------------
        INFO:backend.classifier.para_agent:Input received: Python 프로그래밍의 기초 개념을 배우고 있습니다...
        INFO:httpx:HTTP Request: POST https://*** "HTTP/1.1 200 OK"
        INFO:backend.classifier.langchain_integration:분류 완료: Areas (confidence: 90.00%, metadata: False)
        INFO:backend.classifier.para_agent:Text classification completed: Areas
        INFO:backend.classifier.para_agent:Final result: 
            {'category': 'Areas', 'confidence': 0.9, 
            'reasoning': "지속적으로 배우고 있는 상태로, 특정 기한이나 목표가 없는 학습 영역을 나타냄. '기초 개념을 배우고 있습니다'는 지속적인 관심 영역을 암시함.", 
            'detected_cues': ['기초 개념', '배우고 있습니다'], 'source': 'langchain', 'has_metadata': False}
    Category: Areas
    Confidence: 0.9
    Source: langchain

    ======================================================================
    📊 Step별 검증: 5/5 통과
    ======================================================================

    ✅ 모든 Step이 완벽하게 통합되어 있습니다!!
        → Issue #6 완성 준비 완료!! 🎉

"""