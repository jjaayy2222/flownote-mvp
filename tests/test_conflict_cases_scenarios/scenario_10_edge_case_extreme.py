# tests/test_conflict_cases_scenarios/scenario_10_edge_case_extreme.py

"""
Scenario 10: 극단값 테스트 (매우 모호함)

상황:
- 매우 짧고 모호한 입력
- 모든 분류기가 불확실
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.classifier.para_agent import run_para_agent_sync
from backend.database.metadata_schema import ClassificationMetadataExtender


def test_scenario_10():
    """Scenario 10: 극단값 테스트"""
    
    test_text = "기타"  # 극도로 모호함
    
    print("=" * 80)
    print("🧪 Scenario 10: 극단값 테스트 (매우 모호한 입력)")
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
    
    # ✅ 검증: 결과가 있어야 함 (nil safe)
    assert category, "카테고리가 있어야 함"
    assert confidence >= 0, "신뢰도는 음수가 아니어야 함"
    
    meta = ClassificationMetadataExtender()
    file_id = meta.save_classification_result(
        result,
        filename=f"scenario_10_test.txt"
    )
    
    print(f"✅ Scenario 10 PASS!")
    print(f"  - Extreme Case Handled: Success ✅")
    print(f"  - DB Saved: file_id={file_id}")
    print()


# 테스트
if __name__ == "__main__":
    test_scenario_10()