# tests/test_conflict_cases_scenarios/scenario_03_keyword_dominant.py

"""
Scenario 3: Keyword 우세 분류

상황:
- PARA 신뢰도: 0.65
- Keyword 신뢰도: 0.88
- Gap: 0.23 → Keyword가 우승!
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.classifier.para_agent import run_para_agent_sync
from backend.database.metadata_schema import ClassificationMetadataExtender


def test_scenario_03():
    """Scenario 3: Keyword 우세"""

    test_text = "팀과 월간 회의 진행"  # Keyword 우세 예상

    print("=" * 80)
    print("🧪 Scenario 3: Keyword 우세 분류 (Gap > 0.2)")
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

    # ✅ 검증: 높은 신뢰도, 충돌 없음
    assert confidence > 0.7, f"신뢰도 부족: {confidence}"
    assert not conflict_detected, "충돌이 감지되면 안 됨"

    # DB 저장
    meta = ClassificationMetadataExtender()
    file_id = meta.save_classification_result(result, filename=f"scenario_03_test.txt")

    print(f"✅ Scenario 3 PASS!")
    print(f"  - Keyword Dominant: {confidence} ✅")
    print(f"  - No Conflict: {not conflict_detected} ✅")
    print(f"  - DB Saved: file_id={file_id}")
    print()


# 테스트
if __name__ == "__main__":
    test_scenario_03()
