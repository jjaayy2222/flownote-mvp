# tests/test_conflict_cases_scenarios/scenario_02_equal_confidence.py

"""
Scenario 2: 동등 신뢰도 충돌 (충돌 감지 → User Review 필요)

상황:
- PARA 신뢰도: 0.75
- Keyword 신뢰도: 0.75
- Gap: 0.00 → 충돌 감지!
"""

import sys
from pathlib import Path 

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.classifier.para_agent import run_para_agent_sync
from backend.database.metadata_schema import ClassificationMetadataExtender


def test_scenario_02():
    """Scenario 2: 동등 신뢰도 충돌"""
    
    test_text = "회의 준비 및 안건 정리"  # PARA ≈ Keyword (둘 다 0.75 예상)
    
    print("=" * 80)
    print("🧪 Scenario 2: 동등 신뢰도 충돌 (User Review 필요)")
    print("=" * 80)
    print(f"Input: {test_text}")
    print()
    
    result = run_para_agent_sync(test_text)
    
    category = result.get('category', '')
    confidence = result.get('confidence', 0)
    conflict_detected = result.get('conflict_detected', False)
    requires_review = result.get('requires_review', False)
    
    print(f"📊 분류 결과:")
    print(f"  - Category: {category}")
    print(f"  - Confidence: {confidence}")
    print(f"  - Conflict Detected: {conflict_detected}")
    print(f"  - Requires Review: {requires_review}")
    print()
    
    # ✅ 검증: 충돌 감지 & Review 필요
    assert conflict_detected or requires_review, "충돌 감지되지 않음"
    assert confidence > 0.5, f"신뢰도 부족: {confidence}"
    
    # DB 저장
    meta = ClassificationMetadataExtender()
    file_id = meta.save_classification_result(
        result,
        filename=f"scenario_02_test.txt"
    )
    
    print(f"✅ Scenario 2 PASS!")
    print(f"  - Conflict Detected: {conflict_detected} ✅")
    print(f"  - Requires Review: {requires_review} ✅")
    print(f"  - DB Saved: file_id={file_id}")
    print()


# 테스트
if __name__ == "__main__":
    test_scenario_02()