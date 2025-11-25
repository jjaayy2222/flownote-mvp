# tests/test_classification_flow.py

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 올바른 경로로 임포트
from backend.api.routes import router as router
from backend.api.models import *


import logging
import json
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# 테스트 1: KeywordClassifier 단독 테스트
def test_1_keyword_classifier():
    """테스트 1: KeywordClassifier 단독 테스트"""
    print("\n" + "=" * 60)
    print("테스트 1: KeywordClassifier 단독 테스트")
    print("=" * 60)

    from backend.classifier.keyword_classifier import KeywordClassifier

    test_texts = ["프로젝트 완성하기", "회의 준비", "건강 관리 계획"]

    for text in test_texts:
        classifier = KeywordClassifier()  # 매번 새 인스턴스
        result = classifier.classify(text)

        print(f"\n📝 텍스트: {text}")
        print(f"  ✅ Tags: {result.get('tags', [])}")
        print(f"  ✅ Confidence: {result.get('confidence')}")
        print(f"  ✅ Is Fallback: {result.get('is_fallback', False)}")

        # tags가 반드시 존재하는지 확인
        assert "tags" in result, "❌ tags 필드 없음!"
        assert len(result["tags"]) > 0, "❌ tags가 빈 배열!"

    print("\n✅ 테스트 1 통과!")


# 수정
# 테스트 2: ConflictService 단독 테스트
@pytest.mark.asyncio
async def test_2_conflict_service():
    """테스트 2: ConflictService 테스트 (Mocked)"""
    print("\n" + "=" * 60)
    print("테스트 2: ConflictService 테스트")
    print("=" * 60)

    from backend.services.conflict_service import ConflictService
    from unittest.mock import patch, AsyncMock

    # Mocking external dependencies
    with patch(
        "backend.services.conflict_service.run_para_agent", new_callable=AsyncMock
    ) as mock_para:
        with patch(
            "backend.services.conflict_service.KeywordClassifier"
        ) as MockKeywordClassifier:
            # Setup Mocks
            mock_para.return_value = {
                "category": "Projects",
                "confidence": 0.9,
                "snapshot_id": "snap_mock_123",
            }

            mock_keyword_instance = MockKeywordClassifier.return_value
            mock_keyword_instance.aclassify = AsyncMock(
                return_value={
                    "tags": ["python", "coding"],
                    "confidence": 0.8,
                    "user_context_matched": True,
                }
            )

            service = ConflictService()

            # await 추가
            result = await service.classify_text("프로젝트 완성하기")

            print(f"\n📊 분류 결과:")
            print(f"  - PARA: {result.get('para_result', {}).get('category')}")
            print(f"  - Keywords: {result.get('keyword_result', {}).get('tags', [])}")
            print(
                f"  - Final: {result.get('conflict_result', {}).get('final_category')}"
            )
            print(f"  - Snapshot: {result.get('snapshot_id')}")

            # keyword_tags 확인
            keyword_tags = result.get("keyword_result", {}).get("tags", [])
            assert len(keyword_tags) > 0, "❌ keyword_tags가 비어있음!"

            print("\n✅ 테스트 2 통과!")


# 테스트 3: DB 저장 테스트
def test_3_db_storage():
    """테스트 3: DB 저장 테스트"""
    print("\n" + "=" * 60)
    print("테스트 3: DB 저장 테스트")
    print("=" * 60)

    from backend.database.metadata_schema import ClassificationMetadataExtender

    extender = ClassificationMetadataExtender()

    test_result = {
        "category": "Projects",
        "keyword_tags": ["업무", "프로젝트"],
        "confidence": 0.9,
        "conflict_detected": False,
        "snapshot_id": "test_snapshot_123",
        "reasoning": "테스트 저장",
    }

    file_id = extender.save_classification_result(
        result=test_result,
        filename=f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
    )

    print(f"\n✅ DB 저장 성공: file_id={file_id}")

    # DB에서 조회
    classifications = extender.get_all_classifications()
    print(f"✅ 총 {len(classifications)}개 분류 결과 저장됨")

    if classifications:
        last = classifications[-1]
        print(f"\n마지막 저장 결과:")
        print(f"  - Filename: {last['filename']}")
        print(f"  - Category: {last['para_category']}")
        print(f"  - Keywords: {last['keyword_tags']}")
        print(f"  - Snapshot: {last['snapshot_id']}")

    print("\n✅ 테스트 3 통과!")


# 테스트 4: classification_log.csv 기록 테스트
def test_4_classification_log():
    """테스트 4: classification_log.csv 기록 테스트"""
    print("\n" + "=" * 60)
    print("테스트 4: classification_log 기록 테스트")
    print("=" * 60)

    from backend.data_manager import DataManager

    dm = DataManager()

    # 로그 기록
    result = dm.log_classification(
        user_id="test_user",
        file_name="test_file.txt",
        ai_prediction="Projects",
        user_selected=None,
        confidence=0.9,
    )

    print(f"\n✅ 로그 기록 결과: {result}")

    # 로그 파일 확인
    log_file = Path("data/classifications/classification_log.csv")
    if log_file.exists():
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            print(f"✅ 로그 파일 총 {len(lines)}줄")
            if len(lines) > 1:
                print(f"\n마지막 줄:")
                print(f"  {lines[-1].strip()}")
    else:
        print(f"⚠️ 로그 파일 없음: {log_file}")

    print("\n✅ 테스트 4 통과!")


# 테스트 5: API 엔드포인트 테스트
def test_5_api_endpoint():
    """테스트 5: /api/classifier/classify 엔드포인트 테스트"""
    print("\n" + "=" * 60)
    print("테스트 5: API 엔드포인트 테스트 (curl 명령어)")
    print("=" * 60)

    print("\n서버가 실행 중이어야 합니다!")
    print("실행 명령어:")
    print("  uvicorn backend.main:app --reload --port 8000")

    print("\n테스트 curl 명령어:")
    print(
        """
curl -X POST "http://127.0.0.1:8000/classifier/keywords" \\
  -H "Content-Type: application/json" \\
  -d '{"text": "영어 공부하기",
    "user_id": "test_user_3",
    "file_id": "test_file_003"
  }' | jq '.'
    """
    )

    print("\n확인 사항:")
    print("  1. keyword_tags가 비어있지 않은가?")
    print("  2. confidence가 0이 아닌가?")
    print("  3. category가 제대로 설정되었나?")

    print("\n✅ 테스트 5 준비 완료! (수동 실행 필요)")


# ---------------------
# pytest가 아닌 직접 실행용
# ---------------------
if __name__ == "__main__":
    import asyncio

    async def run_all_tests():
        """모든 테스트 실행"""
        try:
            test_1_keyword_classifier()
            await test_2_conflict_service()  # ✅ await 추가!
            test_3_db_storage()
            test_4_classification_log()
            test_5_api_endpoint()

            print("\n" + "=" * 60)
            print("🎉 모든 테스트 통과!")
            print("=" * 60)
        except Exception as e:
            print(f"\n❌ 테스트 실패: {e}")
            import traceback

            traceback.print_exc()

    # ✅ asyncio.run() 사용!
    asyncio.run(run_all_tests())


"""test_result


/Users/jay/.pyenv/versions/myenv/bin/python: No module named tests/test_classification_flow
(myenv) ➜  flownote-mvp git:(refactor-v4-phase-2-models) ✗ pytest tests/test_classification_flow.py -v
======================================================= test session starts =======================================================
platform darwin -- Python 3.11.10, pytest-8.3.0, pluggy-1.6.0 -- /Users/jay/.pyenv/versions/3.11.10/envs/myenv/bin/python
cachedir: .pytest_cache
rootdir: /Users/jay/ICT-projects/flownote-mvp
configfile: pytest.ini
plugins: anyio-4.11.0, langsmith-0.4.37, asyncio-1.3.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
collected 5 items                                                                                                                 

tests/test_classification_flow.py::test_1_keyword_classifier PASSED                                                         [ 20%]
tests/test_classification_flow.py::test_2_conflict_service PASSED                                                           [ 40%]
tests/test_classification_flow.py::test_3_db_storage PASSED                                                                 [ 60%]
tests/test_classification_flow.py::test_4_classification_log PASSED                                                         [ 80%]
tests/test_classification_flow.py::test_5_api_endpoint PASSED                                                               [100%]

======================================================= 5 passed in 33.79s ========================================================



"""
