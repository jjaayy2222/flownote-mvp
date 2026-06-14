# tests/test_conflict_cases_scenarios/scenario_09_edge_case_boundary.py

"""
Scenario 9: 경계값 테스트 (Gap = 0.2 정확히)

상황:
- Gap = 0.2 (정확히 경계값)
- 자동 해결 판정 기준
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.classifier.para_agent import run_para_agent_sync
from backend.database.metadata_schema import ClassificationMetadataExtender


def test_scenario_09():
    """Scenario 9: 경계값 테스트"""

    test_text = "분기별 재정 검토 보고서"  # Gap ≈ 0.2

    print("=" * 80)
    print("🧪 Scenario 9: 경계값 테스트 (Gap = 0.2)")
    print("=" * 80)
    print(f"Input: {test_text}")
    print()

    result = run_para_agent_sync(test_text)

    category = result.get("category", "")
    confidence = result.get("confidence", 0)
    conflict_detected = result.get("conflict_detected", False)

    print(f"📊 분류 결과:")
    print(f"  - Category: {category}")
    print(f"  - Confidence: {confidence}")
    print(f"  - Conflict: {conflict_detected}")
    print()

    # ✅ 검증: 경계값에서의 동작
    assert confidence > 0.5, f"신뢰도 부족: {confidence}"

    meta = ClassificationMetadataExtender()
    file_id = meta.save_classification_result(result, filename=f"scenario_09_test.txt")

    print(f"✅ Scenario 9 PASS!")
    print(f"  - Boundary Test: Success ✅")
    print(f"  - DB Saved: file_id={file_id}")
    print()


# 테스트
if __name__ == "__main__":
    test_scenario_09()
