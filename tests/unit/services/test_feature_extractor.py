# tests/unit/services/test_feature_extractor.py

import pytest
from backend.services.feature_extractor import FeatureExtractor, FileFeatures

@pytest.fixture
def extractor():
    return FeatureExtractor()

def test_extract_basic_features(extractor):
    """기본 텍스트 및 구조 특징 추출 테스트"""
    content = """
    # Project Plan
    This is an urgent task.
    - [ ] Todo item 1
    - [x] Todo item 2
    
    Deadline: 2025-12-31
    """
    metadata = {"tags": ["work", "important"], "reference_count": 2}
    usage = {"access_count": 10, "days_since_access": 1}
    
    # 동기 호출로 변경됨
    features = extractor.extract(content, metadata, usage)
    
    # 텍스트 분석
    assert features.text_length > 0
    assert features.word_count > 0
    
    # 구조 분석
    assert features.has_checklist is True
    assert features.has_deadline is True
    assert features.has_code_block is False
    
    # 관계 분석
    assert features.tag_count == 2
    assert features.reference_count == 2
    
    # 긴급성 분석
    assert "urgent" in features.urgency_indicators
    assert "deadline" in features.urgency_indicators

def test_extract_empty_content(extractor):
    """빈 콘텐츠 처리 테스트"""
    features = extractor.extract("", {}, {})
    
    assert features.text_length == 0
    assert features.word_count == 0
    assert features.has_checklist is False
    assert features.sentiment_score == 0.0

def test_extract_temporal_features(extractor):
    """시간 특징 계산 테스트"""
    usage = {
        "access_count": 10,
        "days_since_access": 4,  # 빈도 = 10 / 5 = 2.0
        "edit_count": 5,
        "days_since_edit": 9     # 빈도 = 5 / 10 = 0.5
    }
    
    features = extractor.extract("test", {}, usage)
    
    assert features.days_since_access == 4
    assert features.access_frequency == pytest.approx(2.0)
    assert features.edit_frequency == pytest.approx(0.5)

def test_extract_temporal_features_negative_values(extractor):
    """시간 특징 음수 값 처리 테스트 (PR Feedback)"""
    usage = {
        "access_count": 10,
        "days_since_access": -5,  # 음수 -> 999로 처리
        "edit_count": 5,
        "days_since_edit": -1     # 음수 -> 999로 처리
    }
    
    features = extractor.extract("test", {}, usage)
    
    assert features.days_since_access == 999
    assert features.days_since_edit == 999
    # 빈도 계산 시 분모가 1000이 되므로 매우 작은 값
    assert features.access_frequency == pytest.approx(0.01)   # 10 / 1000
    assert features.edit_frequency == pytest.approx(0.005)    # 5 / 1000

def test_extract_temporal_features_default_usage_stats(extractor):
    """기본 usage_stats 처리 테스트 (PR Feedback)"""
    # usage_stats가 비어있는 경우
    usage = {}
    
    features = extractor.extract("test", {}, usage)
    
    # 기본값 확인
    assert features.days_since_access == 999
    assert features.days_since_edit == 999
    assert features.access_frequency == pytest.approx(0.0)
    assert features.edit_frequency == pytest.approx(0.0)

def test_extract_temporal_features_negative_counts_clamped_to_zero(extractor):
    """음수 access/edit count가 0으로 클램핑되는지 테스트 (PR Feedback)"""
    usage = {
        "days_since_access": 4,
        "days_since_edit": 9,
        "access_count": -10,
        "edit_count": -5,
    }

    features = extractor.extract("test", {}, usage)

    assert features.access_frequency == pytest.approx(0.0)
    assert features.edit_frequency == pytest.approx(0.0)

def test_extract_sentiment(extractor):
    """감정 분석 테스트"""
    # 문장부호가 있어도 잘 동작해야 함 (PR Feedback)
    positive_text = "Great job! Success is near."
    negative_text = "This is a terrible bug, and failure."
    
    pos_features = extractor.extract(positive_text, {}, {})
    neg_features = extractor.extract(negative_text, {}, {})
    
    assert pos_features.sentiment_score > 0
    assert neg_features.sentiment_score < 0

def test_extract_code_block(extractor):
    """코드 블록 감지 테스트"""
    content = """
    Here is some code:
    ```python
    print("Hello")
    ```
    """
    features = extractor.extract(content, {}, {})
    assert features.has_code_block is True

def test_extract_deadline_from_metadata(extractor):
    """메타데이터의 deadline 필드로 마감 기한 감지 테스트 (PR Feedback)"""
    content = """
    # Random Notes
    This document does not mention any due dates or deadlines in the text.
    """
    metadata = {"deadline": "2025-12-31"}
    usage = {}

    features = extractor.extract(
        file_content=content,
        file_metadata=metadata,
        usage_stats=usage,
    )

    assert features.has_deadline is True

@pytest.mark.parametrize(
    "content, expected_checklist",
    [
        ("- [ ] item 1\n- [x] item 2", True),
        ("* [ ] item 1\n* [x] item 2", True),
        ("-   [X] item with spaces", True),
        ("No checklist here", False),
    ],
)
def test_extract_checklist_regex_variations(extractor, content, expected_checklist):
    """체크리스트 정규식 변형 패턴 테스트 (PR Feedback)"""
    features = extractor.extract(content, {}, {})
    assert features.has_checklist == expected_checklist