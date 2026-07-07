# backend/exceptions.py

"""
FlowNote MVP - Custom Exception Hierarchy (커스텀 예외 클래스 계층 구조).

[KO] 백엔드 전역에서 사용되는 커스텀 예외 클래스를 정의합니다.
     호출자(API 라우터 등)는 각 예외 타입에 따라 아래에 명시된 HTTP 상태 코드를 결정론적으로 매핑해야 합니다.
[EN] Defines custom exception classes used globally across the backend.
     Callers (e.g., API routers) should deterministically map HTTP status codes
     based on the specific exception type as documented below.
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
    [KO] 파일 유효성 검증 실패 시 발생하는 예외. → HTTP 422 (Unprocessable Entity)
         입력 파일 자체는 수신되었으나, 의미론적 검증 규칙을 통과하지 못한 경우에 사용합니다.
         - 허용되지 않는 파일 확장자가 업로드된 경우
         - 파일 크기 제한을 초과한 경우
    [EN] Raised when file validation fails. → HTTP 422 (Unprocessable Entity)
         Use when the file is received but fails semantic validation rules.
         - An unsupported file extension is uploaded.
         - The file size exceeds the allowed limit.
    """


class QueryValidationError(FlowNoteError):
    """
    [KO] 검색 쿼리 유효성 검증 실패 시 발생하는 예외. → HTTP 400 (Bad Request)
         클라이언트가 잘못된 형식의 요청 데이터를 전송한 경우에 사용합니다.
         - 검색어가 최소 길이 미만으로 너무 짧은 경우
         - 공백 문자만으로 구성된 검색어가 입력된 경우
    [EN] Raised when search query validation fails. → HTTP 400 (Bad Request)
         Use when the client sends a malformed or invalid request payload.
         - The search term is too short (below minimum length).
         - The input consists of only whitespace characters.
    """


class APIKeyError(FlowNoteError):
    """
    [KO] API 키 설정 오류 시 발생하는 예외. → HTTP 503 (Service Unavailable)
         서버가 외부 서비스에 연결할 수 없는 구성 문제로, 클라이언트 요청 자체의 잘못이 아닌 경우에 사용합니다.
         - 환경 변수에 API 키가 설정되지 않은 경우
         - 설정된 API 키가 유효하지 않은 경우
    [EN] Raised when an API key configuration error is detected. → HTTP 503 (Service Unavailable)
         Use when a server-side configuration issue prevents connection to an external service,
         not due to a client-side error.
         - The API key is not set in environment variables.
         - The configured API key is invalid or rejected.
    """


class EmbeddingError(FlowNoteError):
    """
    [KO] 임베딩(Embedding) 생성 처리 중 오류 발생 시 사용하는 예외. → HTTP 502 (Bad Gateway)
         외부 임베딩 서비스로부터 유효한 응답을 받지 못한 경우에 사용합니다.
         - 외부 임베딩 모델 API 호출에 실패한 경우
         - 임베딩 벡터 생성 결과가 예상과 다른 형식인 경우

         `error_type` 필드를 통해 장애 원인을 분류하여 관측성(Observability)을 제공합니다.
         (예: "timeout", "connection", "api_error")

    [EN] Raised when an error occurs during embedding generation. → HTTP 502 (Bad Gateway)
         Use when the server fails to receive a valid response from an external embedding service.
         - The external embedding model API call fails.
         - The resulting embedding vector has an unexpected format.

         The `error_type` field classifies the failure cause for improved observability.
         (e.g., "timeout", "connection", "api_error")
    """

    def __init__(self, message: str = "", error_type: str = "api_error"):
        super().__init__(message)
        self.error_type = error_type


class SearchError(FlowNoteError):
    """
    [KO] 검색 및 조회 처리 과정에서 오류 발생 시 사용하는 예외. → HTTP 500 (Internal Server Error)
         서버 내부의 검색 파이프라인에서 예기치 않은 오류가 발생한 경우에 사용합니다.
         - 벡터 검색 인덱스 또는 텍스트 검색 엔진에서 조회 실패가 발생한 경우
         - 복합 검색 결과 병합 과정에서 예외가 발생한 경우
    [EN] Raised when an error occurs during search or retrieval. → HTTP 500 (Internal Server Error)
         Use when an unexpected failure occurs in the server-side search pipeline.
         - A retrieval failure occurs in the vector search index or text search engine.
         - An exception occurs while merging combined search results.
    """
