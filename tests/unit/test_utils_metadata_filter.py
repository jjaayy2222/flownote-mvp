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
    """None 값에 대한 매칭 세만틱 검증 (엄격한 가치 기반 필터링)."""
    # 1. 필터가 스칼라 None인 경우 -> 모든 값에 대해 매칭 (와일드카드성 동작 유지)
    assert check_metadata_match({"category": "A"}, {"category": None}) is True
    assert check_metadata_match({}, {"category": None}) is True

    # 2. 필터에 명시적 값이 있는데 문서가 None/누락인 경우 -> 매칭 실패 (방어적)
    assert check_metadata_match({"category": None}, {"category": "A"}) is False
    assert check_metadata_match({}, {"category": "A"}) is False

    # 3. 필터 리스트에 None과 유효 값이 섞인 경우 -> 유효 값 기준으로만 판정
    doc_none = {"tags": None}
    doc_val = {"tags": ["AI"]}
    filter_mix = {"tags": ["AI", None]}  # None은 무시되고 "AI"만 필터로 작동

    assert check_metadata_match(doc_none, filter_mix) is False
    assert check_metadata_match(doc_val, filter_mix) is True
