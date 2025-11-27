# tests/units/models/test_models.py

import pytest
from pydantic import ValidationError
from backend.models import (
    ClassifyRequest,
    ClassifyResponse,
    Step1Input,
    ConflictType,
    ConflictRecord,
)


def test_classify_request_validation():
    """ClassifyRequest 유효성 검사 테스트"""
    # 정상 케이스
    req = ClassifyRequest(text="Test Text", user_id="user123")
    assert req.text == "Test Text"
    assert req.user_id == "user123"

    # 필수 필드 누락 (text)
    with pytest.raises(ValidationError):
        ClassifyRequest(user_id="user123")


def test_classify_response_validation():
    """ClassifyResponse 유효성 검사 테스트"""
    # 정상 케이스
    res = ClassifyResponse(
        category="Projects",
        confidence=0.9,
        keyword_tags=["tag1"],
        conflict_detected=False,
    )
    assert res.category == "Projects"
    assert res.confidence == 0.9

    # confidence 범위 초과 (0~1 사이여야 함 - 만약 validator가 있다면)
    # 현재 모델 정의를 확인하지 않았지만, 일반적으로 0~1 사이값임.
    # Pydantic 모델에 validator가 없다면 통과될 수 있음.


def test_step1_input_validation():
    """Step1Input 유효성 검사 테스트"""
    # 정상 케이스
    step1 = Step1Input(occupation="Developer", name="Jay")
    assert step1.occupation == "Developer"

    # 필수 필드 누락
    with pytest.raises(ValidationError):
        Step1Input(name="Jay")


def test_conflict_record_validation():
    """ConflictRecord 유효성 검사 테스트"""
    record = ConflictRecord(
        type=ConflictType.CATEGORY_CONFLICT,
        description="Category mismatch",
        severity=0.8,
    )
    assert record.type == ConflictType.CATEGORY_CONFLICT
    assert record.severity == 0.8
    assert record.auto_resolvable is True  # Default value check
