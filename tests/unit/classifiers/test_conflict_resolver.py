# tests/test_conflict_resolver.py

import pytest
from dataclasses import dataclass
from typing import List


@dataclass
class ClassificationResult:
    """분류 결과 표준 형식"""
    category: str
    confidence: float
    source: str
    reasoning: str = ""
    tags: List[str] = None


def test_clear_winner_para():
    """Test 1: PARA wins with clear confidence gap"""
    from backend.classifier.conflict_resolver import ConflictResolver
    
    resolver = ConflictResolver(confidence_gap_threshold=0.2)
    
    para = ClassificationResult(
        category="Projects",
        confidence=0.92,
        source="para",
        reasoning="Clear deadline exists"
    )
    
    keyword = ClassificationResult(
        category="업무",
        confidence=0.65,
        source="keyword",
        tags=["업무", "회의"]
    )
    
    result = resolver.resolve(para, keyword)
    
    assert result["final_category"] == "Projects"
    assert result["conflict_detected"] == False
    assert result["requires_review"] == False
    assert result["winner_source"] == "para"
    print("PASSED: Test 1 - Clear winner (PARA)")


def test_requires_user_review():
    """Test 2: Confidence gap too small - needs review"""
    from backend.classifier.conflict_resolver import ConflictResolver
    
    resolver = ConflictResolver(confidence_gap_threshold=0.2)
    
    para = ClassificationResult(
        category="Areas",
        confidence=0.73,
        source="para"
    )
    
    keyword = ClassificationResult(
        category="학습",
        confidence=0.72,
        source="keyword",
        tags=["학습"]
    )
    
    result = resolver.resolve(para, keyword)
    
    assert result["conflict_detected"] == True
    assert result["requires_review"] == True
    assert result["confidence_gap"] < 0.2
    print("PASSED: Test 2 - Requires user review")


def test_keyword_wins():
    """Test 3: Keyword wins with higher confidence"""
    from backend.classifier.conflict_resolver import ConflictResolver
    
    resolver = ConflictResolver(confidence_gap_threshold=0.2)
    
    para = ClassificationResult(
        category="Resources",
        confidence=0.60,
        source="para"
    )
    
    keyword = ClassificationResult(
        category="업무",
        confidence=0.88,
        source="keyword",
        tags=["업무", "프로젝트"]
    )
    
    result = resolver.resolve(para, keyword)
    
    assert result["winner_source"] == "keyword"
    assert result["confidence"] == 0.88
    assert result["conflict_detected"] == False
    print("PASSED: Test 3 - Keyword wins")


if __name__ == "__main__":
    try:
        test_clear_winner_para()
    except ImportError as e:
        print(f"Not ready: {e}")
    
    try:
        test_requires_user_review()
    except ImportError as e:
        print(f"Not ready: {e}")
    
    try:
        test_keyword_wins()
    except ImportError as e:
        print(f"Not ready: {e}")



"""test_conflict_resolver_resyult

    ================================ test session starts ==================================
    platform darwin -- Python 3.11.10, pytest-8.3.0, pluggy-1.6.0 -- /Users/jay/.pyenv/versions/3.11.10/envs/myenv/bin/python
    cachedir: .pytest_cache
    rootdir: /Users/jay/ICT-projects/flownote-mvp
    plugins: anyio-4.11.0, langsmith-0.4.37
    collected 3 items                                                                      

    tests/test_conflict_resolver.py::test_clear_winner_para PASSED                   [ 33%]
    tests/test_conflict_resolver.py::test_requires_user_review PASSED                [ 66%]
    tests/test_conflict_resolver.py::test_keyword_wins PASSED                        [100%]

    ================================== 3 passed in 0.03s ===================================

"""