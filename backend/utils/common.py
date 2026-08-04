# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/utils.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - 코어 유틸리티 모듈.

애플리케이션 전반에서 재사용되는 핵심 유틸리티 함수들을 제공합니다.
환경 변수 파싱, 로깅, 토큰 계산 등 공통 기능을 담당합니다.

FlowNote MVP - Core Utilities Module.

Provides core utility functions reused throughout the application.
Handles common functionalities such as environment variable parsing, logging, and token calculation.
"""

import hashlib
import logging
import os
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import tiktoken  # type: ignore[import]

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 상수 및 설정 값
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

INVALID_PII_SENTINEL = "<INVALID_PII>"
ANONYMOUS_USER_ID = "anonymous"
MAX_QUERY_PREVIEW_LEN = 200

# ―――――――――――――――――――――――――
# 에러 로깅 유틸리티 (Error Logging Utilities)
# ―――――――――――――――――――――――――

_DEFAULT_MAX_ERROR_LOG_LENGTH = 100

# Unix / Windows 절대 경로 패턴 — OSError 메시지의 주요 PII 노출 원인
# Unix/Windows absolute path pattern — primary PII risk in OSError messages
_SENSITIVE_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|/)(?:[\w.\-\\/]+)")


def safe_parse_env_int(
    env_var_name: str, default: int, min_val: Optional[int] = None
) -> int:
    """
    [KO]
    환경 변수를 정수형(int)으로 안전하게 파싱합니다.
    실패 시 로그를 남기고 기본값을 반환합니다.

    Args:
        env_var_name: 파싱할 환경 변수의 이름
        default: 파싱 실패 시 반환할 기본값
        min_val: 허용되는 최소값 (지정 시 이보다 작으면 기본값 반환)

    Returns:
        파싱된 정수값 또는 기본값

    [EN]
    Safely parses an environment variable into an integer.
    Logs a warning and returns the default value upon failure.

    Args:
        env_var_name: The name of the environment variable to parse
        default: The default value to return if parsing fails
        min_val: The minimum allowed value (returns default if parsed value is smaller)

    Returns:
        The parsed integer or the default value
    """
    val = os.getenv(env_var_name)
    if val is None:
        return default
    try:
        parsed = int(val)
        if min_val is not None and parsed < min_val:
            logger.warning(
                "환경 변수 '%s'의 값(%s)은 최소 %s 이상이어야 합니다. 기본값 %s을(를) 사용합니다.",
                env_var_name,
                val,
                min_val,
                default,
            )
            return default
        return parsed
    except ValueError:
        logger.warning(
            "환경 변수 '%s'의 값(%s)을 int로 파싱할 수 없습니다. 기본값 %s을(를) 사용합니다.",
            env_var_name,
            val,
            default,
        )
        return default


def safe_parse_env_float(
    env_var_name: str, default: float, min_val: Optional[float] = None
) -> float:
    """
    [KO]
    환경 변수를 실수형(float)으로 안전하게 파싱합니다.
    실패 시 로그를 남기고 기본값을 반환합니다.

    Args:
        env_var_name: 파싱할 환경 변수의 이름
        default: 파싱 실패 시 반환할 기본값
        min_val: 허용되는 최소값 (지정 시 이보다 작으면 기본값 반환)

    Returns:
        파싱된 실수값 또는 기본값

    [EN]
    Safely parses an environment variable into a float.
    Logs a warning and returns the default value upon failure.

    Args:
        env_var_name: The name of the environment variable to parse
        default: The default value to return if parsing fails
        min_val: The minimum allowed value (returns default if parsed value is smaller)

    Returns:
        The parsed float or the default value
    """
    val = os.getenv(env_var_name)
    if val is None:
        return default
    try:
        parsed = float(val)
        if min_val is not None and parsed < min_val:
            logger.warning(
                "환경 변수 '%s'의 값(%s)은 최소 %s 이상이어야 합니다. 기본값 %s을(를) 사용합니다.",
                env_var_name,
                val,
                min_val,
                default,
            )
            return default
        return parsed
    except ValueError:
        logger.warning(
            "환경 변수 '%s'의 값(%s)을 float으로 파싱할 수 없습니다. 기본값 %s을(를) 사용합니다.",
            env_var_name,
            val,
            default,
        )
        return default


# \ud658\uacbd\ubcc0\uc218\ub85c \uc870\uc815 \uac00\ub2a5; \uc798\ubabb\ub41c \uac12 \uc785\ub825 \uc2dc safe_parse_env_int\uc774 \uae30\ubcf8\uac12 \uc0ac\uc6a9 + warning \ub85c\uae45
# Configurable via env var; safe_parse_env_int uses default + warning on invalid input
MAX_ERROR_LOG_LENGTH: int = safe_parse_env_int(
    "FLOWNOTE_MAX_ERROR_LOG_LENGTH", _DEFAULT_MAX_ERROR_LOG_LENGTH, min_val=1
)


def format_error_msg(e: Exception, mask_paths: Optional[bool] = None) -> str:
    """
    [KO]
    Exception 메시지에서 파일 경로를 마스킹하고, 환경 변수로 설정된 최대 길이로 잘라내는 공용 헬퍼.
    - mask_paths=None (기본값): OSError 등 파일 경로가 포함되는 예외 타입인 경우 파일 경로를 [REDACTED_PATH]로 자동 치환 후 최대 길이 축약
    - mask_paths=True: 예외 타입과 무관하게 파일 경로 마스킹 강제 적용
    - mask_paths=False: 경로 마스킹을 수행하지 않고 최대 길이 축약만 적용

    Args:
        e: 처리할 예외 객체 (Exception)
        mask_paths: 경로 마스킹 여부 (None일 경우 OSError 타입일 때 자동 마스킹)

    Returns:
        마스킹 및 축약 처리된 에러 메시지 문자열

    [EN]
    Shared helper that masks file paths in Exception messages and truncates to the
    configured max length.
    - mask_paths=None (default): Automatically replaces file paths with [REDACTED_PATH] for file-related exceptions like OSError.
    - mask_paths=True: Forces path masking regardless of exception type.
    - mask_paths=False: Bypasses path masking and applies truncation only.

    Args:
        e: The exception instance to format
        mask_paths: Whether to apply path masking (None auto-masks for OSError)

    Returns:
        The formatted, masked, and truncated error message string
    """
    err_msg = str(e)
    should_mask = mask_paths if mask_paths is not None else isinstance(e, OSError)
    if should_mask:
        err_msg = _SENSITIVE_PATH_RE.sub("[REDACTED_PATH]", err_msg)
    if len(err_msg) > MAX_ERROR_LOG_LENGTH:
        return f"{err_msg[:MAX_ERROR_LOG_LENGTH]}..."
    return err_msg


def mask_pii_id(value: Optional[str], truncate_len: int = 12) -> str:
    """
    [KO]
    민감 문자열(user_id, session_id 등)을 SHA-256으로 해시화하는 중앙 유틸리티입니다.
    로그에 개인정보(PII)가 노출되지 않도록 안전하게 마스킹합니다.

    Args:
        value: 마스킹할 원본 문자열
        truncate_len: 반환할 해시 문자열의 최대 길이 (기본값 12)
            - 0이면 전체 해시 문자열 반환
            - 음수 전달 시 0으로 정규화(안전 폴백)하여 전체 반환

    Returns:
        안전하게 마스킹된 해시 문자열 또는 INVALID_PII_SENTINEL

    [EN]
    Central utility to hash sensitive strings (e.g., user_id, session_id) using SHA-256.
    Safely masks Personally Identifiable Information (PII) to prevent log exposure.

    Args:
        value: The original string to mask
        truncate_len: Maximum length of the returned hash string (default 12)
            - If 0, returns the full hash string
            - If negative, normalizes to 0 (safe fallback) and returns full

    Returns:
        Safely masked hash string or INVALID_PII_SENTINEL
    """
    if not value or not isinstance(value, str):
        return INVALID_PII_SENTINEL

    # [Security Validation] 음수 방어(Safe Wrapper)
    safe_len = max(0, truncate_len)

    hashed = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return hashed[:safe_len] if safe_len > 0 else hashed


def get_chat_log_extra(request_or_body: Any) -> Dict[str, Any]:
    """
    [KO]
    채팅 엔드포인트에서 공통으로 사용하는 안전한 로깅 딕셔너리를 생성합니다.
    입력 객체의 형태를 검사하여 (dict 또는 BaseModel 등) 안전하게 필드를 추출하고 민감 정보를 마스킹 처리합니다.

    Args:
        request_or_body: 파싱할 요청 객체 또는 딕셔너리

    Returns:
        마스킹된 사용자 ID와 축약된 쿼리 문자열이 포함된 딕셔너리

    [EN]
    Creates a safe logging dictionary commonly used across chat endpoints.
    Inspects the input object type (dict or BaseModel) to safely extract fields and mask sensitive information.

    Args:
        request_or_body: The request object or dictionary to parse

    Returns:
        A dictionary containing the masked user ID and truncated query string
    """
    if isinstance(request_or_body, Mapping):
        raw_user_id = request_or_body.get("user_id")
        raw_query = request_or_body.get("query")
    else:
        raw_user_id = getattr(request_or_body, "user_id", None)
        raw_query = getattr(request_or_body, "query", None)

    # Truthy 체크를 통해 빈 문자열("")이나 0 같은 Falsy 값에 대해서도
    # 안전하게 ANONYMOUS_USER_ID 로 폴백하도록 기존 동작 복원
    safe_user_id = str(raw_user_id) if raw_user_id else ANONYMOUS_USER_ID
    safe_query = str(raw_query) if raw_query else ""

    is_truncated = len(safe_query) > MAX_QUERY_PREVIEW_LEN
    truncated_query = safe_query[:MAX_QUERY_PREVIEW_LEN] + (
        "..." if is_truncated else ""
    )

    return {
        "user_id_hash": mask_pii_id(safe_user_id),
        "query_preview": truncated_query,
    }


def check_metadata_match(
    doc_metadata: Optional[Dict[str, Any]], metadata_filter: Optional[Dict[str, Any]]
) -> bool:
    """
    [KO]
    문서의 메타데이터가 지정된 필터 조건에 부합하는지 확인합니다.
    OR 시맨틱을 적용하여 문서의 값 중 하나라도 필터 후보군에 포함되는지 검사합니다.
    빈 리스트 필터([])는 유효한 매칭 후보가 없는 것으로 간주하여 즉시 False를 반환합니다.

    Args:
        doc_metadata: 문서에서 추출한 메타데이터 딕셔너리
        metadata_filter: 적용할 필터 조건

    Returns:
        모든 필터 조건을 만족하면 True, 하나라도 불일치하면 False

    [EN]
    Checks if the document's metadata matches the specified filter conditions.
    Applies OR semantics to check if any document value is included in the filter candidates.
    An empty list filter ([]) is considered to have no valid matching candidates, returning False immediately.

    Args:
        doc_metadata: The metadata dictionary extracted from the document
        metadata_filter: The filter conditions to apply

    Returns:
        True if all conditions are met, False if any condition fails
    """
    if not metadata_filter:
        return True

    # 메타데이터가 없는 경우 (필터는 존재하는데 데이터가 없음)
    if not isinstance(doc_metadata, dict):
        return False

    for filter_key, filter_value in metadata_filter.items():
        # 1. 존재성 확인: 필터에서 요구하는 키가 문서에 아예 없는 경우 실패
        if filter_key not in doc_metadata:
            return False

        doc_value = doc_metadata[filter_key]

        # 2. 빈 리스트 필터([]) 처리: 어떤 값과도 매칭될 수 없으므로 False (보안 정책)
        if isinstance(filter_value, list) and not filter_value:
            return False

        # 3. 리스트 정규화 및 교집합 검사 (None 포함)
        filter_raw = filter_value if isinstance(filter_value, list) else [filter_value]
        doc_raw = doc_value if isinstance(doc_value, list) else [doc_value]

        # OR 세만틱: 문서 값 중 하나라도 필터 후보군에 포함되는지 확인
        if set(doc_raw).isdisjoint(filter_raw):
            return False

    return True


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """
    [KO]
    주어진 텍스트와 모델에 대한 토큰 수를 계산합니다.
    tiktoken을 사용하여 정확한 토큰 수를 산출하며, 실패 시 단순 문자 길이 기반 휴리스틱(문자수 // 4)으로 대체합니다.

    Args:
        text: 토큰 수를 계산할 텍스트
        model: 기준이 되는 모델명 (기본값: "gpt-4")

    Returns:
        계산된 토큰 수

    [EN]
    Calculates the number of tokens for a given text and model.
    Uses tiktoken for accurate calculation, falling back to a simple character length heuristic (char length // 4) on failure.

    Args:
        text: The text to count tokens for
        model: The reference model name (default: "gpt-4")

    Returns:
        The calculated number of tokens
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except Exception:
        # 대략적인 계산 (1 token ≈ 4 characters)
        return len(text) // 4


def read_file_content(file_path: str) -> str:
    """
    [KO]
    지정된 경로의 파일 내용을 읽어 문자열로 반환합니다.

    Args:
        file_path: 읽어올 파일의 경로

    Returns:
        파일의 텍스트 내용

    Raises:
        RuntimeError: 파일 읽기에 실패했을 때 발생

    [EN]
    Reads the contents of a file at the specified path and returns it as a string.

    Args:
        file_path: The path of the file to read

    Returns:
        The text content of the file

    Raises:
        RuntimeError: Raised when reading the file fails
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        raise RuntimeError(f"파일 읽기 실패: {str(e)}") from e


def format_file_size(size_bytes: int) -> str:
    """
    [KO]
    바이트 단위의 파일 크기를 사람이 읽기 쉬운 형식(B, KB, MB, GB, TB)으로 변환합니다.

    Args:
        size_bytes: 변환할 파일 크기(바이트)

    Returns:
        변환된 문자열 포맷

    [EN]
    Converts a file size in bytes to a human-readable format (B, KB, MB, GB, TB).

    Args:
        size_bytes: The file size in bytes to convert

    Returns:
        The formatted file size string
    """
    # [Validation] 음수 용량 예외 방어
    current_size: float = max(0.0, float(size_bytes))
    for unit in ["B", "KB", "MB", "GB"]:
        if current_size < 1024.0:
            return f"{current_size:.1f} {unit}"
        current_size /= 1024.0
    return f"{current_size:.1f} TB"


def estimate_cost(tokens: int, cost_per_token: float) -> float:
    """
    [KO]
    총 토큰 수와 토큰당 단가를 기반으로 예상 비용(USD)을 추정합니다.

    Args:
        tokens: 사용된 전체 토큰 수
        cost_per_token: 1 토큰당 비용

    Returns:
        추정된 총 비용

    [EN]
    Estimates the expected cost (in USD) based on total tokens and cost per token.

    Args:
        tokens: The total number of tokens used
        cost_per_token: The cost per single token

    Returns:
        The estimated total cost
    """
    return tokens * cost_per_token


def load_pdf(file) -> str:
    """
    [KO]
    Streamlit 인터페이스를 통해 업로드된 PDF 파일에서 텍스트를 추출합니다.

    Args:
        file: Streamlit의 UploadedFile 객체

    Returns:
        PDF에서 추출된 전체 텍스트

    Raises:
        RuntimeError: pypdf 라이브러리가 설치되지 않았을 때, 또는 PDF 읽기 실패 시
            (예외 유형 포함: ``PDF 읽기 실패: ExcType: 메시지`` 형식으로 디버깅 지원)

    [EN]
    Extracts text from a PDF file uploaded via the Streamlit interface.

    Args:
        file: The UploadedFile object from Streamlit

    Returns:
        The complete text extracted from the PDF

    Raises:
        RuntimeError: Raised when pypdf is not installed, or when PDF reading fails.
            Format: ``PDF 읽기 실패: ExcType: message``
            (note: the ``PDF 읽기 실패`` prefix is Korean-localized)
    """
    try:
        from pypdf import PdfReader  # type: ignore[import]
        from pypdf.errors import PyPdfError  # type: ignore[import]
    except ImportError as e:
        raise RuntimeError("pypdf 라이브러리가 설치되어 있지 않습니다.") from e

    try:
        # PDF 리더 생성
        pdf_reader = PdfReader(file)

        # 모든 페이지의 텍스트 추출 (리스트 컴프리헨션 및 join 사용으로 성능 최적화)
        pages_text = []
        for page in pdf_reader.pages:
            if extracted := page.extract_text():
                pages_text.append(extracted)

        return "\n".join(pages_text).strip()

    except (PyPdfError, ValueError, OSError) as e:
        # PDF 파싱 오류(PyPdfError), 잘못된 입력값(ValueError), 또는 I/O 오류(OSError)
        raise RuntimeError(f"PDF 읽기 실패: {type(e).__name__}: {e}") from e


def save_to_markdown(text: str, filepath: str, title: str = "Untitled"):
    """
    [KO]
    추출된 텍스트를 지정된 경로에 마크다운(.md) 파일로 저장합니다.
    디렉터리가 존재하지 않으면 자동으로 생성하고, 문서 상단에 메타데이터를 추가합니다.

    Args:
        text: 저장할 본문 텍스트
        filepath: 생성할 마크다운 파일의 절대 또는 상대 경로
        title: 문서 상단 헤더에 들어갈 제목 (기본값: "Untitled")

    [EN]
    Saves the extracted text to a Markdown (.md) file at the specified path.
    Automatically creates parent directories if they do not exist, and prepends metadata to the top of the document.

    Args:
        text: The body text to save
        filepath: The absolute or relative path for the generated markdown file
        title: The title to insert at the top header of the document (default: "Untitled")
    """
    # 디렉토리 생성
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)

    # 마크다운 형식으로 저장
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n")
        f.write(f"생성일: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("---\n\n")
        f.write(text)
