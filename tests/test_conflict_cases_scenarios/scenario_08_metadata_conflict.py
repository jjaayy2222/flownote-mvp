# tests/test_conflict_cases_scenarios/scenario_08_metadata_conflict.py

"""
Scenario 8: 메타데이터 충돌 (다중 정보 충돌)

상황:
- PARA와 Keyword 모두 높은 신뢰도이지만 다른 분류
- 메타데이터 상충
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.classifier.para_agent import run_para_agent_sync
from backend.database.metadata_schema import ClassificationMetadataExtender


def test_scenario_08():
    """Scenario 8: 메타데이터 충돌"""
    
    test_text = "회사 정책 변경 검토"  # 메타데이터 충돌 예상
    
    print("=" * 80)
    print("🧪 Scenario 8: 메타데이터 충돌 (다중 정보 상충)")
    print("=" * 80)
    print(f"Input: {test_text}")
    print()
    
    result = run_para_agent_sync(test_text)
    
    category = result.get('category', '')
    confidence = result.get('confidence', 0)
    conflict_detected = result.get('conflict_detected', False)
    
    print(f"📊 분류 결과:")
    print(f"  - Category: {category}")
    print(f"  - Confidence: {confidence}")
    print(f"  - Conflict Detected: {conflict_detected}")
    print()
    
    # ✅ 검증: 카테고리 유효성
    assert category in ["Projects", "Areas", "Resources", "Archive"], f"예상 카테고리 불일치: {category}"
    assert confidence > 0, "신뢰도가 있어야 함"
    
    meta = ClassificationMetadataExtender()
    file_id = meta.save_classification_result(
        result,
        filename=f"scenario_08_test.txt"
    )
    
    print(f"✅ Scenario 8 PASS!")
    print(f"  - Category: {category} ✅")
    print(f"  - DB Saved: file_id={file_id}")
    print()


# 테스트
if __name__ == "__main__":
    test_scenario_08()