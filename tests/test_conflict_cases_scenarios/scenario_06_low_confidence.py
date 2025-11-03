# tests/test_conflict_cases_scenarios/scenario_06_low_confidence.py

"""
Scenario 6: 신뢰도 낮음 (판단 어려움)

상황:
- 모든 분류 신뢰도 < 0.6
- Review 필요 (User 판단 대기)
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.classifier.para_agent import run_para_agent_sync
from backend.database.metadata_schema import ClassificationMetadataExtender


def test_scenario_06():
    """Scenario 6: 신뢰도 낮음"""
    
    test_text = "기타 활동"  # 모호함
    
    print("=" * 80)
    print("🧪 Scenario 6: 신뢰도 낮음 (판단 어려움)")
    print("=" * 80)
    print(f"Input: {test_text}")
    print()
    
    result = run_para_agent_sync(test_text)
    
    category = result.get('category', '')
    confidence = result.get('confidence', 0)
    requires_review = result.get('requires_review', False)
    
    print(f"📊 분류 결과:")
    print(f"  - Category: {category}")
    print(f"  - Confidence: {confidence}")
    print(f"  - Requires Review: {requires_review}")
    print()
    
    # ✅ 검증: 낮은 신뢰도
    assert confidence < 0.7, f"신뢰도가 높아야 함: {confidence}"
    
    meta = ClassificationMetadataExtender()
    file_id = meta.save_classification_result(
        result,
        filename=f"scenario_06_test.txt"
    )
    
    print(f"✅ Scenario 6 PASS!")
    print(f"  - Low Confidence: {confidence} ✅")
    print(f"  - DB Saved: file_id={file_id}")
    print()

# 테스트
if __name__ == "__main__":
    test_scenario_06()