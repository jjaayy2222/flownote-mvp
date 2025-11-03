# tests/test_conflict_cases_scenarios/runner.py

import sys
from pathlib import Path

# ✅ 프로젝트 루트 경로 추가
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.test_conflict_cases_scenarios.scenario_01_auto_confidence import test_scenario_01
from tests.test_conflict_cases_scenarios.scenario_02_equal_confidence import test_scenario_02
from tests.test_conflict_cases_scenarios.scenario_03_keyword_dominant import test_scenario_03
from tests.test_conflict_cases_scenarios.scenario_04_para_dominant import test_scenario_04
from tests.test_conflict_cases_scenarios.scenario_05_large_gap import test_scenario_05
from tests.test_conflict_cases_scenarios.scenario_06_low_confidence import test_scenario_06
from tests.test_conflict_cases_scenarios.scenario_07_review_required import test_scenario_07
from tests.test_conflict_cases_scenarios.scenario_08_metadata_conflict import test_scenario_08
from tests.test_conflict_cases_scenarios.scenario_09_edge_case_boundary import test_scenario_09
from tests.test_conflict_cases_scenarios.scenario_10_edge_case_extreme import test_scenario_10


def run_all_scenarios():
    """모든 시나리오를 순차적으로 실행"""
    
    print("\n" + "=" * 80)
    print("🚀 충돌 해결 테스트 스위트 시작!")
    print("=" * 80)
    
    scenarios = [
        ("01", "자동 신뢰도 해결", test_scenario_01),
        ("02", "동등 신뢰도 충돌", test_scenario_02),
        ("03", "Keyword 우세", test_scenario_03),
        ("04", "PARA 우세", test_scenario_04),
        ("05", "신뢰도 차이 큼", test_scenario_05),
        ("06", "신뢰도 낮음", test_scenario_06),
        ("07", "Review 필요", test_scenario_07),
        ("08", "메타데이터 충돌", test_scenario_08),
        ("09", "경계값 테스트", test_scenario_09),
        ("10", "극단값 테스트", test_scenario_10),
    ]
    
    passed = 0
    failed = 0
    
    for idx, (num, name, test_func) in enumerate(scenarios, 1):
        try:
            print(f"\n[{idx}/10] Scenario {num}: {name} 실행...")
            test_func()
            passed += 1
            
        except AssertionError as e:
            print(f"\n❌ Scenario {num} FAILED: {e}")
            failed += 1
            
        except Exception as e:
            print(f"\n❌ Scenario {num} ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    # 결과 요약
    print("\n" + "=" * 80)
    print(f"📊 테스트 결과:")
    print(f"  ✅ Passed: {passed}/10")
    print(f"  ❌ Failed: {failed}/10")
    print("=" * 80)
    
    if failed == 0:
        print("🎉 모든 시나리오 완벽하게 PASS!")
    else:
        print(f"⚠️  {failed}개 시나리오 확인 필요")

# 테스트
if __name__ == "__main__":
    run_all_scenarios()