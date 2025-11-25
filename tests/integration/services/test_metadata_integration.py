# tests/test_metadata_integration.py

import pytest
from backend.classifier.conflict_resolver import ConflictResolver, ClassificationResult


def test_metadata_with_auto_resolution():
    """자동 해결 시 메타데이터 기록"""
    resolver = ConflictResolver(confidence_gap_threshold=0.2)
    
    para = ClassificationResult(
        category="Projects",
        confidence=0.92,
        source="para",
        reasoning="Clear deadline"
    )
    
    keyword = ClassificationResult(
        category="업무",
        confidence=0.60,
        source="keyword",
        tags=["urgent", "deadline"]
    )
    
    result = resolver.resolve(para, keyword)
    
    assert result["final_category"] == "Projects"
    assert result["confidence_gap"] == pytest.approx(0.32, rel=0.01)
    assert result["conflict_detected"] == False
    assert result["resolution_method"] == "auto_by_confidence"
    assert result["para_reasoning"] == "Clear deadline"
    assert result["keyword_tags"] == ["urgent", "deadline"]
    print("PASSED: Metadata with auto resolution")


def test_metadata_with_conflict():
    """충돌 시 상세 메타데이터"""
    resolver = ConflictResolver(confidence_gap_threshold=0.2)
    
    para = ClassificationResult(
        category="Areas",
        confidence=0.75,
        source="para",
        reasoning="Related to skill development"
    )
    
    keyword = ClassificationResult(
        category="학습",
        confidence=0.73,
        source="keyword",
        tags=["python", "AI"]
    )
    
    result = resolver.resolve(para, keyword)
    
    assert result["conflict_detected"] == True
    assert result["requires_review"] == True
    assert "confidence_gap" in result
    assert "reason" in result
    assert "모호" in result["reason"]
    print("PASSED: Metadata with conflict")


def test_statistics():
    """통계 정보 생성"""
    resolver = ConflictResolver(confidence_gap_threshold=0.2)
    
    for i in range(5):
        para = ClassificationResult(
            category="Projects",
            confidence=0.9 - (i * 0.05),
            source="para"
        )
        keyword = ClassificationResult(
            category="업무",
            confidence=0.6,
            source="keyword"
        )
        resolver.resolve(para, keyword)
    
    stats = resolver.get_statistics()
    
    assert stats["total_resolutions"] == 5
    assert stats["auto_resolve_rate"] >= 0.6
    print("PASSED: Statistics generation")


if __name__ == "__main__":
    test_metadata_with_auto_resolution()
    test_metadata_with_conflict()
    test_statistics()
    print("\n✅ 모든 테스트 통과!!")



"""test_metadata_integration test_result_2

    ➀ `pytest tests/test_conflict_resolver -v` → ConflictResolver 기본 구조 + 3개 테스트 ✅

    ➁ `pytest tests/test_metadata_integration.py -v` → 메타데이터 통합 + 통계 기능 ✅

    ============================== test session starts ==============================
    platform darwin -- Python 3.11.10, pytest-8.3.0, pluggy-1.6.0 -- /Users/jay/.pyenv/versions/3.11.10/envs/myenv/bin/python
    cachedir: .pytest_cache
    rootdir: /Users/jay/ICT-projects/flownote-mvp
    plugins: anyio-4.11.0, langsmith-0.4.37
    collected 3 items                                                               

    tests/test_metadata_integration.py::test_metadata_with_auto_resolution PASSED [ 33%]
    tests/test_metadata_integration.py::test_metadata_with_conflict PASSED    [ 66%]
    tests/test_metadata_integration.py::test_statistics PASSED                [100%]

    =============================== 3 passed in 0.01s ===============================

    ⇒ PARA vs Keyword 분류 결과를 신뢰도 기반으로 자동 해결하고, 메타데이터 저장 + 통계 기능까지 완료!

"""