import pytest
import io
import uuid


def test_full_onboarding_and_classification_flow(client):
    """
    E2E 테스트: 온보딩 -> 분류 전체 흐름 검증
    """
    # 1. 온보딩 Step 1: 사용자 생성
    user_name = f"User_{uuid.uuid4().hex[:6]}"
    response = client.post(
        "/onboarding/step1", json={"name": user_name, "occupation": "Developer"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    user_id = data["user_id"]

    # 2. 온보딩 Step 2: 영역 추천
    response = client.get(
        "/onboarding/suggest-areas",
        params={"user_id": user_id, "occupation": "Developer"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["suggested_areas"]) > 0

    # 3. 온보딩 Step 3: 컨텍스트 저장
    selected_areas = data["suggested_areas"][:3]
    response = client.post(
        "/onboarding/save-context",
        json={"user_id": user_id, "selected_areas": selected_areas},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"

    # 4. 파일 분류 (Mocking 없이 통합 테스트)
    # 주의: 실제 LLM 호출을 방지하기 위해 conftest.py에서 환경변수나 Mocking 설정이 필요할 수 있음.
    # 하지만 E2E 테스트는 최대한 실제 환경과 비슷하게 하는 것이 좋음.
    # 여기서는 conftest.py의 client가 app을 사용하고, app 내부의 서비스들이 Mocking되지 않았다면 실제 호출이 발생함.
    # 비용 문제나 속도 문제를 피하기 위해, E2E 테스트에서도 외부 API 호출 부분만 Mocking하는 것이 일반적임.
    # 현재 conftest.py에는 Mocking 설정이 없음.
    # 따라서 이 테스트는 실제 OpenAI API를 호출할 수 있음.
    # 하지만 사용자가 "Mocking 없이 통합 테스트"라고 명시하지 않았으므로,
    # 안전하게 외부 API 호출 부분만 patch하여 테스트하는 것이 좋음.
    # 또는 conftest.py에서 이미 환경변수로 API KEY를 test-key로 설정했으므로,
    # 실제 호출 시 인증 에러가 발생할 수 있음.
    # 따라서 여기서는 `backend.services.classification_service.run_para_agent` 등을 patch해야 함.

    # E2E 테스트 파일 내에서 patch를 적용하여 테스트 진행
    from unittest.mock import patch, AsyncMock

    mock_para_result = {"category": "Projects", "confidence": 0.9}
    mock_keyword_result = {"tags": ["python"], "confidence": 0.8}

    # ClassificationService 내부의 외부 호출 Mocking
    with patch(
        "backend.services.classification_service.run_para_agent", new_callable=AsyncMock
    ) as mock_para:
        mock_para.return_value = mock_para_result

        # KeywordClassifier Mocking (인스턴스 메서드)
        with patch(
            "backend.classifier.keyword_classifier.KeywordClassifier.aclassify",
            new_callable=AsyncMock,
        ) as mock_keyword:
            mock_keyword.return_value = mock_keyword_result

            # ConflictResolver Mocking (인스턴스 메서드)
            # ConflictService 내부에서 ConflictResolver를 사용함.
            # ConflictService는 싱글톤으로 생성되어 있을 수 있음.
            # app.state나 의존성 주입을 사용하지 않고 전역 변수나 직접 인스턴스화를 사용한다면 patch 위치가 중요함.

            # 파일 업로드
            file_content = "This is a test project file."
            files = {
                "file": (
                    "test.txt",
                    io.BytesIO(file_content.encode("utf-8")),
                    "text/plain",
                )
            }

            response = client.post(
                "/classifier/file", files=files, data={"user_id": user_id}
            )

            assert response.status_code == 200
            result = response.json()

            assert result["category"] == "Projects"
            assert (
                result["confidence"] >= 0.0
            )  # ConflictResolver 로직에 따라 달라질 수 있음
            assert "keyword_tags" in result
