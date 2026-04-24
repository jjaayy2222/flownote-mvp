# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/utils.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - 유틸리티 함수
"""

import os
import logging
import tiktoken  # type: ignore[import]
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 새로 추가하는 함수들
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

INVALID_PII_SENTINEL = "<INVALID_PII>"


def safe_parse_env_int(
    env_var_name: str, default: int, min_val: Optional[int] = None
) -> int:
    """환경 변수를 int로 안전하게 파싱합니다. 실패 시 로그를 남기고 기본값을 반환합니다."""
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
    """환경 변수를 float으로 안전하게 파싱합니다. 실패 시 로그를 남기고 기본값을 반환합니다."""
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


def mask_pii_id(value: Optional[str], truncate_len: int = 12) -> str:
    """
    민감 문자열(user_id, session_id 등)을 SHA-256 해시화하여
    로그에 안전하게 기록하기 위한 중앙 유틸리티.

    Args:
        value: 마스킹할 원본 문자열
        truncate_len: 반환할 해시 문자열의 최대 길이
            - 기본값 12
            - 0이면 전체 해시 문자열 반환
            - 음수 전달 시 0으로 정규화(안전 폴백) 하여 전체를 반환함
    """
    if not value or not isinstance(value, str):
        return INVALID_PII_SENTINEL

    # [Security Validation] 음수 방어(Safe Wrapper)
    safe_len = max(0, truncate_len)

    hashed = str(hashlib.sha256(value.encode("utf-8")).hexdigest())
    if safe_len > 0:
        return hashed[:safe_len]  # type: ignore[index]
    return hashed


def check_metadata_match(
    doc_metadata: Optional[Dict[str, Any]], metadata_filter: Optional[Dict[str, Any]]
) -> bool:
    """
    문서의 메타데이터가 필터 조건에 부합하는지 확인합니다.

    Args:
        doc_metadata: 문서에서 추출한 메타데이터 딕셔너리
        metadata_filter: 적용할 필터 조건 (예: {"category": "Projects", "tags": ["AI", "Tech"]})
            * 정책: 필터 값이 빈 리스트([])인 경우, 유효한 매칭 후보가 없는 것으로 간주하여
              해당 조건에 대해 즉시 False를 반환합니다.

    Returns:
        bool: 모든 필터 조건을 만족하면 True, 하나라도 불일치하면 False.
              필터가 None이거나 비어있으면 항상 True를 반환합니다.
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
        if not any(v in filter_raw for v in doc_raw):
            return False

    return True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 기존 함수들
# ━━━━━━━━━━━━━━━━━━━━━━━━━━


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """토큰 수 계산"""
    try:
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except Exception:
        # 대략적인 계산 (1 token ≈ 4 characters)
        return len(text) // 4


def read_file_content(file_path: str) -> str:
    """파일 내용 읽기"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        raise Exception(f"파일 읽기 실패: {str(e)}")


def format_file_size(size_bytes: int) -> str:
    """파일 크기를 읽기 쉬운 형식으로 변환"""
    # [Validation] 음수 용량 예외 방어
    current_size: float = max(0.0, float(size_bytes))
    for unit in ["B", "KB", "MB", "GB"]:
        if current_size < 1024.0:
            return f"{current_size:.1f} {unit}"
        current_size /= 1024.0
    return f"{current_size:.1f} TB"


def estimate_cost(tokens: int, cost_per_token: float) -> float:
    """
    토큰 수를 기반으로 비용 추정

    Args:
        tokens: 토큰 수
        cost_per_token: 토큰당 비용

    Returns:
        추정 비용 (USD)
    """
    return tokens * cost_per_token


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 💙 새로 추가하는 함수들
# ━━━━━━━━━━━━━━━━━━━━━━━━━━


def load_pdf(file) -> str:
    """
    Streamlit 업로드된 PDF 파일을 읽어서 텍스트 추출

    Args:
        file: Streamlit UploadedFile 객체

    Returns:
        str: 추출된 텍스트
    """
    try:
        import pypdf  # type: ignore[import]

        # PDF 리더 생성
        pdf_reader = pypdf.PdfReader(file)

        # 모든 페이지의 텍스트 추출
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"

        return text.strip()

    except Exception as e:
        raise Exception(f"PDF 읽기 실패: {str(e)}")


def save_to_markdown(text: str, filepath: str, title: str = "Untitled"):
    """
    텍스트를 마크다운 파일로 저장

    Args:
        text: 저장할 텍스트
        filepath: 저장할 파일 경로
        title: 문서 제목
    """
    # 디렉토리 생성
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)

    # 마크다운 형식으로 저장
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n")
        f.write(f"생성일: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("---\n\n")
        f.write(text)
