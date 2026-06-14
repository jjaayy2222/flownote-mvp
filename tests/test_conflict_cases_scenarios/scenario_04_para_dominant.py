# tests/test_conflict_cases_scenarios/scenario_04_para_dominant.py

"""
Scenario 4: PARA 우세 분류

상황:
- PARA 신뢰도: 0.90
- Keyword 신뢰도: 0.62
- Gap: 0.28 → PARA가 우승!
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.classifier.para_agent import run_para_agent_sync
from backend.database.metadata_schema import ClassificationMetadataExtender


def test_scenario_04():
    """Scenario 4: PARA 우세"""

    test_text = "프로젝트 마감일 계획"  # PARA 우세 예상

    print("=" * 80)
    print("🧪 Scenario 4: PARA 우세 분류 (Gap > 0.2)")
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
    assert category in [
        "Projects",
        "Areas",
        "Resources",
        "Archive",
    ], f"예상 카테고리 불일치: {category}"

    # DB 저장
    meta = ClassificationMetadataExtender()
    file_id = meta.save_classification_result(result, filename=f"scenario_04_test.txt")

    print(f"✅ Scenario 4 PASS!")
    print(f"  - PARA Dominant: {category} ✅")
    print(f"  - Confidence: {confidence} ✅")
    print(f"  - DB Saved: file_id={file_id}")
    print()


# 테스트
if __name__ == "__main__":
    test_scenario_04()
