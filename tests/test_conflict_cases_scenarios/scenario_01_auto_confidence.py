# tests/test_conflict_cases_scenarios/scenario_01_auto_confidence.py

"""
Scenario 1: 자동 신뢰도 해결 (Confidence Gap > 0.2)

상황:
- PARA: 0.9 (높음)
- Keyword: 0.65 (낮음)
- Gap: 0.25 → 자동 해결!
"""

import sys
from pathlib import Path

# ✅ 상대 경로 (프로젝트 루트)
PROJECT_ROOT = Path(__file__).parent.parent.parent  # tests/... → 루트
sys.path.insert(0, str(PROJECT_ROOT))

from backend.classifier.para_agent import run_para_agent_sync
from backend.database.metadata_schema import ClassificationMetadataExtender


def test_scenario_01():
    """Scenario 1: 자동 신뢰도 해결"""
    
    test_text = "프로젝트 문서 작성"  # PARA: 0.9, Keyword: ~0.7
    
    print("=" * 80)
    print("🧪 Scenario 1: 자동 신뢰도 해결 (Gap > 0.2)")
    print("=" * 80)
    print(f"Input: {test_text}")
    print()
    
    # 분류 실행
    result = run_para_agent_sync(test_text)
    
    # 검증
    assert result['para_result']['confidence'] > 0.8, "PARA 신뢰도 부족"
    assert result['conflict_detected'] == False, "충돌이 감지되면 안 됨"
    assert result['reasoning'] == "명확한 승자 선택됨", "해결 방법 확인"
    
    # DB 저장
    meta = ClassificationMetadataExtender()
    file_id = meta.save_classification_result(result, 
                                            filename=f"scenario_01_{result['snapshot_id']}.txt")
    
    print(f"✅ Scenario 1 PASS")
    print(f"  - PARA: {result['para_result']['confidence']}")
    print(f"  - Keyword: {result['keyword_tags']}")
    print(f"  - DB Saved: file_id={file_id}")
    print()


if __name__ == "__main__":
    test_scenario_01()
