import pytest
from backend.utils import check_metadata_match


def test_check_metadata_match_basic():
    """기본적인 스칼라 필드 매칭 검증."""
    doc = {"category": "Projects", "priority": 1}

    assert check_metadata_match(doc, {"category": "Projects"}) is True
    assert check_metadata_match(doc, {"category": "Areas"}) is False
    assert check_metadata_match(doc, {"category": "Projects", "priority": 1}) is True
    assert check_metadata_match(doc, {"category": "Projects", "priority": 2}) is False


def test_check_metadata_match_list_logic():
    """리스트 값이 포함된 복합 매칭 케이스 검증 (Normalization 세만틱)."""
    # 1. 문서: 리스트, 필터: 리스트 (교집합)
    doc_list = {"tags": ["AI", "NLP"]}
    assert check_metadata_match(doc_list, {"tags": ["AI", "Search"]}) is True
    assert check_metadata_match(doc_list, {"tags": ["CV", "Search"]}) is False

    # 2. 문서: 리스트, 필터: 스칼라 (포함 여부)
    assert check_metadata_match(doc_list, {"tags": "AI"}) is True
    assert check_metadata_match(doc_list, {"tags": "CV"}) is False

    # 3. 문서: 스칼라, 필터: 리스트 (필터 후보군 중 하나와 일치)
    doc_scalar = {"status": "active"}
    assert check_metadata_match(doc_scalar, {"status": ["active", "pending"]}) is True
    assert check_metadata_match(doc_scalar, {"status": ["closed", "pending"]}) is False


def test_check_metadata_match_unhashable():
    """해시 불가능한 객체(dict 등)가 포함된 경우의 매칭 검증."""
    doc = {"tags": [{"id": 1, "name": "AI"}, {"id": 2, "name": "NLP"}]}

    # 리스트 내 객체 직접 비교
    assert check_metadata_match(doc, {"tags": [{"id": 1, "name": "AI"}]}) is True
    assert check_metadata_match(doc, {"tags": [{"id": 3, "name": "CV"}]}) is False


def test_check_metadata_match_edge_cases():
    """엣지 케이스 처리 검증 (None, 빈 딕셔너리 등)."""
    # 필터가 None인 경우 항상 통과
    assert check_metadata_match({"a": 1}, None) is True

    # 필터가 빈 딕셔너리인 경우 항상 통과
    assert check_metadata_match({"a": 1}, {}) is True

    # 문서 메타데이터가 없는 경우 (필터는 있는데 데이터가 없음 -> 실패)
    assert check_metadata_match(None, {"category": "Projects"}) is False

    # 찾는 키가 문서에 없는 경우 (필터에 값이 있으면 실패해야 함)
    assert check_metadata_match({"category": "Projects"}, {"priority": 1}) is False


def test_check_metadata_match_none_semantics():
    """None 값 및 빈 리스트에 대한 매칭 세만틱 검증 (엄격한 필터링 모델)."""
    # 1. 필터가 명시적인 None인 경우 -> 문서 값이 실제로 None인 경우만 매칭
    assert check_metadata_match({"category": None}, {"category": None}) is True
    assert check_metadata_match({"category": "A"}, {"category": None}) is False

    # 2. 키 자체가 없는 경우 (필터에서 기대하는데 데이터 없음) -> 매칭 실패 (엄격한 존재성 검증)
    assert check_metadata_match({}, {"category": None}) is False

    # 3. 필터가 빈 리스트([])인 경우 -> 절대로 매치될 수 없음 (Restrictive)
    assert check_metadata_match({"tags": ["AI"]}, {"tags": []}) is False
    assert check_metadata_match({"tags": []}, {"tags": []}) is False
    assert check_metadata_match({}, {"tags": []}) is False

    # 3. 리스트 내에 None과 값이 섞인 경우 -> 일반적인 교집합 논리 작동 (None 포함)
    doc_none = {"tags": None}
    doc_val = {"tags": ["AI"]}
    filter_mix = {"tags": ["AI", None]}

    assert check_metadata_match(doc_none, filter_mix) is True  # None끼리 매칭
    assert check_metadata_match(doc_val, filter_mix) is True  # "AI"끼리 매칭
    assert check_metadata_match({"tags": ["CV"]}, filter_mix) is False
