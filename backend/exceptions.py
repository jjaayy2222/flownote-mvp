# backend/exceptions.py

"""
커스텀 예외 클래스
    - Error(오류)를 관리하는 클래스
    - 구제적으로 에러 처리를 위해 사용하는 카테고리 클래스
"""


class FlowNoteError(Exception):
    """FlowNote 기본 에러 정의"""
    pass


class FileValidationError(FlowNoteError):
    """파일 검증 실패 에러
        - 확장자가 이상하거나 크기가 너무 클 경우"""
    pass


class QueryValidationError(FlowNoteError):
    """쿼리 검증 실패 에러
        - 검색창에 너무 짧은 검색어를 입력한 경우
        - 빈 칸만 입력한 경우"""
    pass


class APIKeyError(FlowNoteError):
    """API 키 설정 오류 에러
        - API 키가 잘못되었거나 없는 경우"""
    pass


class EmbeddingError(FlowNoteError):
    """임베딩 생성 처리 오류 에러
        - 임베딩 생성 실패했을 경우"""
    pass


class SearchError(FlowNoteError):
    """검색 및 조회 처리 오류 에러
        - 검색하는 과정에서 문제가 생겼을 경우"""
    pass