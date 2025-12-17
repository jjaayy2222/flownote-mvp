# tests/unit/services/test_rule_engine.py

import pytest
from backend.services.rule_engine import RuleEngine

@pytest.fixture
def engine():
    return RuleEngine()

def test_match_projects(engine):
    """Projects 카테고리 매칭 테스트"""
    # 1. Explicit keyword
    res1 = engine.evaluate("This is a new project roadmap.")
    assert res1 is not None
    assert res1.category == "Projects"
    assert res1.matched_rule == "project_keyword"
    
    # 2. Deadline
    res2 = engine.evaluate("Task due date: 2025-12-31")
    assert res2 is not None
    assert res2.category == "Projects"
    assert res2.matched_rule == "deadline_pattern"
    
    # 3. Todo list
    res3 = engine.evaluate("- [ ] Task 1\n- [ ] Task 2")
    assert res3 is not None
    assert res3.category == "Projects"
    assert res3.matched_rule == "todo_list"

def test_match_areas(engine):
    """Areas 카테고리 매칭 테스트"""
    # 1. Finance
    res1 = engine.evaluate("Monthly finance report and budget.")
    assert res1 is not None
    assert res1.category == "Areas"
    assert res1.matched_rule == "area_finance"
    
    # 2. Health
    res2 = engine.evaluate("Daily workout routine.")
    assert res2 is not None
    assert res2.category == "Areas"
    assert res2.matched_rule == "area_health" # or routine_keyword depending on priority

def test_match_resources(engine):
    """Resources 카테고리 매칭 테스트"""
    # 1. Explicit keyword
    res1 = engine.evaluate("Python reference guide.")
    assert res1 is not None
    assert res1.category == "Resources"
    assert res1.matched_rule == "resource_keyword"
    
    # 2. Note
    res2 = engine.evaluate("Just a quick note about ideas.")
    assert res2 is not None
    assert res2.category == "Resources"
    assert res2.matched_rule == "note_keyword"
    
    # 3. Code snippet
    res3 = engine.evaluate("```python\nprint('hello')\n```")
    assert res3 is not None
    assert res3.category == "Resources"
    assert res3.matched_rule == "code_snippet"

def test_match_archives(engine):
    """Archives 카테고리 매칭 테스트"""
    # 1. Explicit keyword
    res1 = engine.evaluate("This project is deprecated and archived.")
    assert res1 is not None
    assert res1.category == "Archives"
    assert res1.matched_rule == "archive_keyword"
    
    # 2. Completed
    res2 = engine.evaluate("Status: completed.")
    assert res2 is not None
    assert res2.category == "Archives"
    assert res2.matched_rule == "completed_status"

def test_priority_highest_confidence(engine):
    """여러 규칙 매칭 시 가장 높은 신뢰도 선택"""
    # "note"(Resources, 0.6) vs "project"(Projects, 0.7)
    text = "This is a project note."
    result = engine.evaluate(text)
    
    assert result is not None
    assert result.category == "Projects"
    assert result.confidence == 0.7
    assert result.matched_rule == "project_keyword"

def test_no_match(engine):
    """매칭되는 규칙이 없는 경우"""
    text = "Just some random text with no specific keywords."
    result = engine.evaluate(text)
    assert result is None

def test_empty_input(engine):
    """빈 입력 처리"""
    assert engine.evaluate("") is None
    assert engine.evaluate(None) is None
