# tests/test_conflict_cases_scenarios/scenario_07_review_required.py

"""
Scenario 7: Review 필요 (requires_review=True)

상황:
- 충돌 감지 또는 신뢰도 낮음
- requires_review 플래그 = True
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.classifier.para_agent import run_para_agent_sync
from backend.database.metadata_schema import ClassificationMetadataExtender


def test_scenario_07():
    """Scenario 7: Review 필요"""
    
    test_text = "프로젝트 회의 및 검토"  # Review 필요 예상
    
    print("=" * 80)
    print("🧪 Scenario 7: Review 필요 (requires_review=True)")
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
    
    # ✅ 검증: Review 필요
    assert requires_review or confidence < 0.75, "Review 플래그 또는 낮은 신뢰도 필요"
    
    meta = ClassificationMetadataExtender()
    file_id = meta.save_classification_result(
        result,
        filename=f"scenario_07_test.txt"
    )
    
    print(f"✅ Scenario 7 PASS!")
    print(f"  - Requires Review: {requires_review} ✅")
    print(f"  - DB Saved: file_id={file_id}")
    print()

# 테스트
if __name__ == "__main__":
    test_scenario_07()