# tests/test_conflict_cases_scenarios/scenario_05_large_gap.py

"""
Scenario 5: 신뢰도 차이 큼 (명확한 승자)

상황:
- PARA 신뢰도: 0.95
- Keyword 신뢰도: 0.45
- Gap: 0.50 → 매우 명확한 승자!
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.classifier.para_agent import run_para_agent_sync
from backend.database.metadata_schema import ClassificationMetadataExtender


def test_scenario_05():
    """Scenario 5: 신뢰도 차이 큼"""

    test_text = "연도별 전략 수립 및 검토"  # PARA > Keyword (큰 차이)

    print("=" * 80)
    print("🧪 Scenario 5: 신뢰도 차이 큼 (Clear Winner)")
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

    # ✅ 검증: 매우 높은 신뢰도, 충돌 없음
    assert confidence > 0.85, f"신뢰도가 매우 높아야 함: {confidence}"
    assert not conflict_detected, "충돌이 감지되면 안 됨"

    # DB 저장
    meta = ClassificationMetadataExtender()
    file_id = meta.save_classification_result(result, filename=f"scenario_05_test.txt")

    print(f"✅ Scenario 5 PASS!")
    print(f"  - Very High Confidence: {confidence} ✅")
    print(f"  - Clear Winner: {category} ✅")
    print(f"  - DB Saved: file_id={file_id}")
    print()


# 테스트
if __name__ == "__main__":
    test_scenario_05()
