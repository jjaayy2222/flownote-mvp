import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.services.classification_service import ClassificationService
from backend.models import ClassifyResponse


@pytest.fixture
def classification_service():
    return ClassificationService()


@pytest.mark.asyncio
async def test_empty_text_input(classification_service):
    """
    엣지 케이스: 빈 텍스트 입력
    기대 결과: 에러 없이 처리되거나, 적절한 기본값(Inbox/Resources) 반환
    """
    # PARA Agent Mock (빈 텍스트라도 호출될 수 있음)
    with patch(
        "backend.classifier.hybrid_classifier.HybridClassifier.classify",
        new_callable=AsyncMock,
    ) as mock_para:
        mock_para.return_value = {"category": "Inbox", "confidence": 0.0}

        # 빈 텍스트 요청
        result = await classification_service.classify(text="")

        assert isinstance(result, ClassifyResponse)
        # 빈 텍스트는 보통 분류가 불가능하므로 신뢰도가 낮거나 Inbox여야 함
        assert result.category in ["Inbox", "Resources"]


@pytest.mark.asyncio
async def test_long_text_input(classification_service):
    """
    엣지 케이스: 매우 긴 텍스트 (10,000자)
    기대 결과: 잘림(Truncation) 처리 등을 통해 에러 없이 수행
    """
    long_text = "project " * 2000  # "project " 8자 * 2000 = 16,000자

    # PARA Agent Mock
    with patch(
        "backend.classifier.hybrid_classifier.HybridClassifier.classify",
        new_callable=AsyncMock,
    ) as mock_para:
        mock_para.return_value = {"category": "Projects", "confidence": 0.9}

        result = await classification_service.classify(text=long_text)

        assert result.category == "Projects"
        assert result.confidence > 0.0


@pytest.mark.asyncio
async def test_gpt_failure_fallback(classification_service):
    """
    엣지 케이스: GPT(PARA) 호출 실패 시 Fallback
    기대 결과: KeywordClassifier 결과만으로 응답 생성
    """
    # PARA Agent가 예외를 발생시키도록 Mock
    with patch(
        "backend.classifier.hybrid_classifier.HybridClassifier.classify",
        side_effect=Exception("GPT API Error"),
    ) as mock_para:

        # 텍스트는 키워드 포함
        text = "urgent deadline task"

        result = await classification_service.classify(text=text)

        # PARA가 실패했으므로 로그에 에러가 찍히고,
        # ClassificationService._run_para_classification의 예외 처리 로직에 따라
        # 기본값(Resources, 0.0)을 반환하거나, Keyword 결과가 있다면 그것을 사용해야 함.

        # 현재 로직상 PARA 실패 -> Resources(0.0) 반환
        # 그리고 Keyword 결과(Projects)와 충돌 해결 시도

        # ConflictService도 Mocking하여 Keyword 결과가 선택되도록 유도하거나,
        # 실제 로직이 Keyword를 선택하는지 확인

        # 여기서는 에러가 전파되지 않고 응답이 오는지만 확인
        assert isinstance(result, ClassifyResponse)
        # KeywordClassifier가 'urgent'를 잡았다면 Projects가 될 가능성 높음
        # 하지만 ConflictService 로직에 따라 달라질 수 있음
        assert result.category in ["Projects", "Resources"]


@pytest.mark.asyncio
async def test_log_save_failure_resilience(classification_service):
    """
    엣지 케이스: 로그 저장 실패 (파일 시스템 오류)
    기대 결과: 사용자 응답에는 영향 없이 성공 반환
    """
    # _save_results 메서드가 예외를 발생시키도록 Mock
    # 주의: _save_results는 내부 메서드이므로 클래스 자체를 patch하거나
    # 인스턴스의 메서드를 교체해야 함

    with patch.object(
        classification_service, "_save_results", side_effect=Exception("Disk Full")
    ):
        with patch(
            "backend.classifier.hybrid_classifier.HybridClassifier.classify",
            new_callable=AsyncMock,
        ) as mock_para:
            mock_para.return_value = {"category": "Projects", "confidence": 0.9}

            # 정상적인 분류 요청
            result = await classification_service.classify(text="test project")

            # 로그 저장이 실패했어도 결과는 정상 반환되어야 함
            assert result.category == "Projects"
            # log_info에 에러 정보가 없거나 비어있을 수 있음 (구현에 따라 다름)
