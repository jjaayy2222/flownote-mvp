# backend/validators.py

"""
FlowNote MVP - Input Validation Module (입력 검증 모듈).

[KO] 사용자 입력(파일, 검색어, API 키 등)이 시스템에 진입하기 전에
     유효성 검사를 수행하는 '입력 문지기' 역할의 모듈입니다.
     - FileValidator  : 업로드 파일의 크기 및 확장자 검증
     - QueryValidator : 검색 쿼리의 길이 및 내용 검증
     - APIKeyValidator: 환경 변수에 설정된 API 키 및 Base URL 검증

[EN] Acts as the 'gatekeeper' module that validates user inputs
     (files, search queries, API keys, etc.) before they enter the system.
     - FileValidator  : Validates file size and extension
     - QueryValidator : Validates query length and content
     - APIKeyValidator: Validates API keys and base URLs from environment variables
"""

import os
from pathlib import Path
from typing import List, Optional, Tuple

from backend.config import ModelConfig


class ValidationError(Exception):
    """
    [KO] 입력 검증 실패 시 발생하는 커스텀 예외 클래스.
    [EN] Custom exception raised when input validation fails.
    """


class FileValidator:
    """
    [KO] 업로드 파일의 유효성을 검증하는 클래스.
         파일 크기 제한과 허용 확장자 규칙을 적용합니다.
    [EN] Validates uploaded files against size limits and allowed extension rules.
    """

    def __init__(
        self,
        max_file_size_mb: int = 200,
        allowed_extensions: Optional[List[str]] = None,
    ) -> None:
        """
        [KO] FileValidator를 초기화합니다.
             max_file_size_mb(int): 허용되는 최대 파일 크기 (단위: MB). 기본값 200.
             allowed_extensions(Optional[List[str]]): 허용 확장자 목록.
                 기본값 ['.pdf', '.txt', '.md'].
        [EN] Initialize FileValidator.
             max_file_size_mb(int): Maximum allowed file size in megabytes. Defaults to 200.
             allowed_extensions(Optional[List[str]]): List of permitted file extensions.
                 Defaults to ['.pdf', '.txt', '.md'].
        """
        self.max_file_size_mb = max_file_size_mb
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.allowed_extensions = allowed_extensions or [
            ".pdf",
            ".txt",
            ".md",
        ]

    def validate_file_size(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        [KO] 파일 크기를 검증합니다.
             빈 파일이거나 설정된 최대 크기를 초과하면 검증에 실패합니다.
             file_path(str): 검증할 파일의 경로 문자열.
             반환값(Tuple[bool, Optional[str]]): (is_valid, error_message) 형태의 튜플.
             검증 성공 시 (True, None), 실패 시 (False, 오류 메시지 문자열).
        [EN] Validates the size of a file.
             Fails if the file is empty or exceeds the configured maximum size.
             file_path(str): Path string of the file to validate.
             Returns(Tuple[bool, Optional[str]]): A tuple of (is_valid, error_message).
             Returns (True, None) on success, (False, error string) on failure.
        """
        try:
            file_size = os.path.getsize(file_path)

            if file_size == 0:
                return False, "❌ 빈 파일입니다."

            if file_size > self.max_file_size_bytes:
                size_mb = file_size / (1024 * 1024)
                return (
                    False,
                    f"❌ 파일 크기가 너무 큽니다. ({size_mb:.1f}MB > {self.max_file_size_mb}MB)",
                )

            return True, None

        except OSError as e:
            return False, f"❌ 파일 크기 확인 중 오류: {str(e)}"

    def validate_extension(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        [KO] 파일 확장자를 검증합니다.
             허용된 확장자 목록에 없는 파일은 검증에 실패합니다.
             file_path(str): 검증할 파일의 경로 문자열.
             반환값(Tuple[bool, Optional[str]]): (is_valid, error_message) 형태의 튜플.
             검증 성공 시 (True, None), 실패 시 (False, 오류 메시지 문자열).
        [EN] Validates the file extension.
             Fails if the extension is not in the list of allowed extensions.
             file_path(str): Path string of the file to validate.
             Returns(Tuple[bool, Optional[str]]): A tuple of (is_valid, error_message).
             Returns (True, None) on success, (False, error string) on failure.
        """
        ext = Path(file_path).suffix.lower()

        if ext in self.allowed_extensions:
            return True, None

        allowed = ", ".join(self.allowed_extensions)
        return (
            False,
            f"❌ 지원하지 않는 파일 형식입니다. ({ext})\n지원 형식: {allowed}",
        )

    def validate_file(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        [KO] 파일에 대한 종합 검증을 순서대로 실행합니다.
             파일 존재 여부 → 확장자 검증 → 크기 검증 순으로 진행하며,
             첫 번째 실패 시 즉시 반환합니다.
             file_path(str): 검증할 파일의 경로 문자열.
             반환값(Tuple[bool, Optional[str]]): (is_valid, error_message) 형태의 튜플.
             모든 검증 통과 시 (True, None), 실패 시 (False, 오류 메시지 문자열).
        [EN] Runs comprehensive validation on a file in sequential order:
             existence check → extension check → size check.
             Returns immediately on the first failure.
             file_path(str): Path string of the file to validate.
             Returns(Tuple[bool, Optional[str]]): A tuple of (is_valid, error_message).
             Returns (True, None) if all checks pass, (False, error string) on failure.
        """
        if not os.path.exists(file_path):
            return False, f"❌ 파일이 존재하지 않습니다: {file_path}"

        valid, error = self.validate_extension(file_path)
        if valid:
            valid, error = self.validate_file_size(file_path)

        return valid, error


class QueryValidator:
    """
    [KO] 검색 쿼리의 유효성을 검증하는 클래스.
         빈 입력, 공백 전용 입력, 길이 제한 규칙을 적용합니다.
    [EN] Validates search queries against blank input, whitespace-only input,
         and minimum/maximum length rules.
    """

    def __init__(
        self,
        min_length: int = 2,
        max_length: int = 500,
    ) -> None:
        """
        [KO] QueryValidator를 초기화합니다.
             min_length(int): 허용되는 최소 쿼리 길이 (공백 제거 후 기준). 기본값 2.
             max_length(int): 허용되는 최대 쿼리 길이 (공백 제거 후 기준). 기본값 500.
        [EN] Initialize QueryValidator.
             min_length(int): Minimum allowed query length (after stripping whitespace). Defaults to 2.
             max_length(int): Maximum allowed query length (after stripping whitespace). Defaults to 500.
        """
        self.min_length = min_length
        self.max_length = max_length

    def validate_query(self, query: str) -> Tuple[bool, Optional[str]]:
        """
        [KO] 검색 쿼리를 검증합니다.
             None/빈 문자열/공백 전용 문자열 및 최소/최대 길이 조건을 순서대로 확인합니다.
             query(str): 검증할 검색 쿼리 문자열.
             반환값(Tuple[bool, Optional[str]]): (is_valid, error_message) 형태의 튜플.
             검증 성공 시 (True, None), 실패 시 (False, 오류 메시지 문자열).
        [EN] Validates a search query.
             Checks for None/empty/whitespace-only string and min/max length in order.
             query(str): Search query string to validate.
             Returns(Tuple[bool, Optional[str]]): A tuple of (is_valid, error_message).
             Returns (True, None) on success, (False, error string) on failure.
        """
        if not query or not query.strip():
            return False, "⚠️ 검색어를 입력해주세요."

        query_length = len(query.strip())

        if query_length < self.min_length:
            return (
                False,
                f"⚠️ 검색어가 너무 짧습니다. (최소 {self.min_length}자)",
            )

        if query_length > self.max_length:
            return (
                False,
                f"⚠️ 검색어가 너무 깁니다. (최대 {self.max_length}자)",
            )

        return True, None


class APIKeyValidator:
    """
    [KO] 환경 변수에 설정된 API 키 및 Base URL의 유효성을 검증하는 클래스.
         개인 정보 보호를 위해 키 값을 직접 인자로 받지 않고,
         backend.config 모듈을 통해 환경 변수에서 간접 로드합니다.
    [EN] Validates API keys and base URLs configured via environment variables.
         To protect sensitive credentials, keys are not accepted as direct arguments
         but are loaded indirectly from environment variables via the backend.config module.
    """

    @staticmethod
    def validate_api_keys() -> Tuple[bool, Optional[str]]:
        """
        [KO] 모든 필수 API 키 및 Base URL에 대한 통합 검증을 실행합니다.
             임베딩 API 키(필수)와 GPT4O API 키(선택)를 순서대로 검증합니다.
             반환값(Tuple[bool, Optional[str]]): (is_valid, error_message) 형태의 튜플.
             모든 검증 통과 시 (True, None), 실패 시 (False, 오류 메시지 문자열).
        [EN] Runs integrated validation for all required API keys and base URLs.
             Validates the Embedding API key (required) and GPT4O API key (optional) in order.
             Returns(Tuple[bool, Optional[str]]): A tuple of (is_valid, error_message).
             Returns (True, None) if all checks pass, (False, error string) on failure.
        """
        embedding_api_key = ModelConfig.EMBEDDING_API_KEY
        embedding_base_url = ModelConfig.EMBEDDING_BASE_URL
        gpt4o_api_key = ModelConfig.GPT4O_API_KEY
        gpt4o_base_url = ModelConfig.GPT4O_BASE_URL

        if not embedding_api_key:
            return (
                False,
                "❌ EMBEDDING_API_KEY가 설정되지 않았습니다.\n.env 파일을 확인하세요.",
            )

        if not embedding_base_url:
            return (
                False,
                "❌ EMBEDDING_BASE_URL이 설정되지 않았습니다.\n.env 파일을 확인하세요.",
            )

        if not embedding_api_key.startswith("eyJ"):
            return (
                False,
                "❌ EMBEDDING_API_KEY 형식이 올바르지 않습니다.\nJWT 토큰이어야 합니다. (eyJ로 시작)",
            )

        if len(embedding_api_key) < 50:
            return (
                False,
                "❌ EMBEDDING_API_KEY가 너무 짧습니다.\n올바른 키인지 확인하세요.",
            )

        if not embedding_base_url.startswith(("http://", "https://")):
            return (
                False,
                "❌ EMBEDDING_BASE_URL이 올바른 URL 형식이 아닙니다.\nhttp:// 또는 https://로 시작해야 합니다.",
            )

        if "mlapi.run" in embedding_base_url and not embedding_base_url.endswith("/v1"):
            return (
                False,
                "⚠️ EMBEDDING_BASE_URL이 /v1로 끝나지 않습니다.\nmlapi.run 프록시는 /v1이 필요합니다.",
            )

        if gpt4o_api_key:
            if not gpt4o_api_key.startswith("eyJ"):
                return (
                    False,
                    "❌ GPT4O_API_KEY 형식이 올바르지 않습니다.\nJWT 토큰이어야 합니다.",
                )

            if not gpt4o_base_url:
                return False, "❌ GPT4O_API_KEY는 있지만 GPT4O_BASE_URL이 없습니다."

        return True, None

    @staticmethod
    def validate_embedding_api() -> Tuple[bool, Optional[str]]:
        """
        [KO] 임베딩 API 키 및 Base URL에 대한 단순 존재 여부 검증을 실행합니다.
             전체 통합 검증(validate_api_keys)보다 가벼운 용도에 사용합니다.
             반환값(Tuple[bool, Optional[str]]): (is_valid, error_message) 형태의 튜플.
             검증 성공 시 (True, None), 실패 시 (False, 오류 메시지 문자열).
        [EN] Runs a lightweight existence check for the Embedding API key and base URL.
             Use this as a simpler alternative to the full validate_api_keys() validation.
             Returns(Tuple[bool, Optional[str]]): A tuple of (is_valid, error_message).
             Returns (True, None) on success, (False, error string) on failure.
        """
        if not ModelConfig.EMBEDDING_API_KEY:
            return False, "❌ 임베딩 API 키가 설정되지 않았습니다."

        if not ModelConfig.EMBEDDING_BASE_URL:
            return (
                False,
                "❌ 임베딩 BASE URL이 설정되지 않았습니다.",
            )

        return True, None
