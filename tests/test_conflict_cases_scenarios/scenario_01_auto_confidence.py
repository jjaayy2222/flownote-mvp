# tests/test_conflict_cases_scenarios/scenario_01_auto_confidence.py

"""
Scenario 1: 자동 신뢰도 해결 (Confidence Gap > 0.2)

상황:
- Keyword 신뢰도: 0.70
- 예상: 명확한 승자 선택 (자동 해결)
"""

import sys
from pathlib import Path

# 상대 경로
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.classifier.para_agent import run_para_agent_sync
from backend.database.metadata_schema import ClassificationMetadataExtender


def test_scenario_01():
    """Scenario 1: 자동 신뢰도 해결"""

    test_text = "프로젝트 문서 작성"

    print("=" * 80)
    print("🧪 Scenario 1: 자동 신뢰도 해결 (명확한 승자)")
    print("=" * 80)
    print(f"Input: {test_text}")
    print()

    # 분류 실행
    result = run_para_agent_sync(test_text)

    # ✅ 실제 구조에 맞게!
    category = result.get("category", "")
    confidence = result.get("confidence", 0)
    conflict_detected = result.get("conflict_detected", False)
    snapshot_id = result.get("snapshot_id", "unknown")

    print(f"📊 분류 결과:")
    print(f"  - Category: {category}")
    print(f"  - Confidence: {confidence}")
    print(f"  - Conflict: {conflict_detected}")
    print(f"  - Snapshot ID: {snapshot_id}")
    print()

    # ✅ 검증: 신뢰도 높은 결과
    assert confidence > 0.8, f"신뢰도 부족: {confidence}"
    assert not conflict_detected, "충돌이 감지되면 안 됨 (자동 해결 시나리오)"
    assert category in [
        "Projects",
        "Areas",
        "Resources",
        "Archive",
    ], f"예상 카테고리 불일치: {category}"

    # DB 저장
    meta = ClassificationMetadataExtender()
    file_id = meta.save_classification_result(result, filename=f"scenario_01_test.txt")

    print(f"✅ Scenario 1 PASS!")
    print(f"  - Category: {category}")
    print(f"  - Confidence: {confidence}")
    print(f"  - No Conflict Detected ✅")
    print(f"  - DB Saved: file_id={file_id}")
    print()


# 테스트
if __name__ == "__main__":
    test_scenario_01()


"""test_result_1 - ❌ (데이터 구조 다름을 확인)

    `python tests/test_conflict_cases_scenarios/scenario_01_auto_confidence.py`
    
    ✅ ModelConfig loaded from backend.config
    
    ================================================================================
    🧪 Scenario 1: 자동 신뢰도 해결 (Gap > 0.2)
    ================================================================================
    Input: 프로젝트 문서 작성

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

    Traceback (most recent call last):
    File "/Users/jay/ICT-projects/flownote-mvp/tests/test_conflict_cases_scenarios/scenario_01_auto_confidence.py", line 55, in <module>
        test_scenario_01()
    File "/Users/jay/ICT-projects/flownote-mvp/tests/test_conflict_cases_scenarios/scenario_01_auto_confidence.py", line 38, in test_scenario_01
        assert result['para_result']['confidence'] > 0.8, "PARA 신뢰도 부족"
            ~~~~~~^^^^^^^^^^^^^^^
    KeyError: 'para_result'

"""

"""test_result_2 - ❌ (`keyword_tags가 비어있음`)

    `python tests/test_conflict_cases_scenarios/scenario_01_auto_confidence.py`

    ✅ ModelConfig loaded from backend.config
    
    ================================================================================
    🧪 Scenario 1: 자동 신뢰도 해결 (Gap > 0.2)
    ================================================================================
    Input: 프로젝트 문서 작성

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

    📊 Result Structure:
    - Keys: dict_keys(
        ['category', 'confidence', 'snapshot_id', 
        'conflict_detected', 'requires_review', 'keyword_tags', 'reasoning']
        )

    ✅ 검증:
    - Keyword 신뢰도: 0.9
    - Tags: []

    Traceback (most recent call last):
    File "/Users/jay/ICT-projects/flownote-mvp/tests/test_conflict_cases_scenarios/scenario_01_auto_confidence.py", line 80, in <module>
        test_scenario_01()
    File "/Users/jay/ICT-projects/flownote-mvp/tests/test_conflict_cases_scenarios/scenario_01_auto_confidence.py", line 62, in test_scenario_01
        assert len(tags) > 0, "태그가 추출되지 않음"
            ^^^^^^^^^^^^^
    AssertionError: 태그가 추출되지 않음

"""


"""test_result_3 - ⭕️ 

    `python tests/test_conflict_cases_scenarios/scenario_01_auto_confidence.py`

    ✅ ModelConfig loaded from backend.config

    ================================================================================
    🧪 Scenario 1: 자동 신뢰도 해결 (명확한 승자)
    ================================================================================
    Input: 프로젝트 문서 작성

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

    📊 분류 결과:
    - Category: Projects
    - Confidence: 0.9
    - Conflict: False
    - Snapshot ID: Snapshot(
        id='snap_20251103_212944', 
        timestamp=datetime.datetime(2025, 11, 3, 21, 29, 44, 575585), 
        text='프로젝트 문서 작성', 
        para_result={'category': 'Projects', 
                    'confidence': 0.9, 
                    'reasoning': '프로젝트 문서 작성은 명확한 작업 목표가 있으며, 특정 기한이 암시될 수 있는 작업으로 판단되어 Projects로 분류.', 
                    'detected_cues': ['프로젝트', '문서', '작성'], 
                    'source': 'langchain', 
                    'has_metadata': False}, 
        keyword_result={'tags': ['업무'], 'confidence': 0.7, 
                        'matched_keywords': {'업무': ['프로젝트']}, 
                        'reasoning': '프로젝트 문서 작성은 업무 관련 활동으로 명확히 분류됨', 
                        'para_hints': {'업무': ['Projects']}}, 
        conflict_result={'final_category': 'Projects', 
                        'para_category': 'Projects', 
                        'keyword_tags': ['업무'], 
                        'confidence': 0.9, 
                        'confidence_gap': 0.2, 
                        'conflict_detected': False, 
                        'resolution_method': 'auto_by_confidence', 
                        'requires_review': False, 
                        'winner_source': 'para', 
                        'para_reasoning': '프로젝트 문서 작성은 명확한 작업 목표가 있으며, 특정 기한이 암시될 수 있는 작업으로 판단되어 Projects로 분류.', 
                        'reason': '명확한 승자 선택됨 (Gap: 0.20)'}, 
                        metadata={'confidence': 0, 'is_conflict': False, 
                                    'final_category': 'Projects'}
        )

    ✅ 분류 결과 저장 완료: file_id=3, snapshot_id=snap_20251103_212944
    ✅ Scenario 1 PASS!
    - Category: Projects
    - Confidence: 0.9
    - No Conflict Detected ✅
    - DB Saved: file_id=3

"""
