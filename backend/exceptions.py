# backend/exceptions.py

"""
FlowNote MVP - Custom Exception Hierarchy (커스텀 예외 클래스 계층 구조).

[KO] 백엔드 전역에서 사용되는 커스텀 예외 클래스를 정의합니다.
     구체적인 에러 카테고리를 통해 호출자(API 라우터 등)가 HTTP 상태 코드를 적절히 매핑할 수 있도록 합니다.
[EN] Defines custom exception classes used globally across the backend.
     Specific error categories allow callers (e.g., API routers) to map appropriate HTTP status codes.
"""


class FlowNoteError(Exception):
    """
    [KO] FlowNote 백엔드 전체에서 사용되는 최상위 기본 예외 클래스.
         모든 커스텀 예외는 이 클래스를 상속합니다.
    [EN] Base exception class for the entire FlowNote backend.
         All custom exceptions inherit from this class.
    """


class FileValidationError(FlowNoteError):
    """
    [KO] 파일 유효성 검증 실패 시 발생하는 예외. (HTTP 400 / 422)
         - 허용되지 않는 파일 확장자가 업로드된 경우
         - 파일 크기 제한을 초과한 경우
    [EN] Raised when file validation fails. (HTTP 400 / 422)
         - An unsupported file extension is uploaded.
         - The file size exceeds the allowed limit.
    """


class QueryValidationError(FlowNoteError):
    """
    [KO] 검색 쿼리 유효성 검증 실패 시 발생하는 예외. (HTTP 400)
         - 검색어가 최소 길이 미만으로 너무 짧은 경우
         - 공백 문자만으로 구성된 검색어가 입력된 경우
    [EN] Raised when search query validation fails. (HTTP 400)
         - The search term is too short (below minimum length).
         - The input consists of only whitespace characters.
    """


class APIKeyError(FlowNoteError):
    """
    [KO] API 키 설정 오류 시 발생하는 예외. (HTTP 500 / 503)
         - 환경 변수에 API 키가 설정되지 않은 경우
         - 설정된 API 키가 유효하지 않은 경우
    [EN] Raised when an API key configuration error is detected. (HTTP 500 / 503)
         - The API key is not set in environment variables.
         - The configured API key is invalid or rejected.
    """


class EmbeddingError(FlowNoteError):
    """
    [KO] 임베딩(Embedding) 생성 처리 중 오류 발생 시 사용하는 예외. (HTTP 502 / 500)
         - 외부 임베딩 모델 API 호출에 실패한 경우
         - 임베딩 벡터 생성 결과가 예상과 다른 형식인 경우
    [EN] Raised when an error occurs during embedding generation. (HTTP 502 / 500)
         - The external embedding model API call fails.
         - The resulting embedding vector has an unexpected format.
    """


class SearchError(FlowNoteError):
    """
    [KO] 검색 및 조회 처리 과정에서 오류 발생 시 사용하는 예외. (HTTP 500)
         - 벡터 DB(FAISS) 또는 BM25 검색 엔진에서 조회 실패가 발생한 경우
         - 하이브리드 검색 결과 병합 과정에서 예외가 발생한 경우
    [EN] Raised when an error occurs during search or retrieval. (HTTP 500)
         - A retrieval failure occurs in the vector DB (FAISS) or BM25 search engine.
         - An exception occurs while merging hybrid search results.
    """
