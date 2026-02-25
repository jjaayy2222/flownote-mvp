# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/utils.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - 유틸리티 함수
"""

import os
import tiktoken
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from datetime import datetime

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 💙 새로 추가하는 함수들
# ━━━━━━━━━━━━━━━━━━━━━━━━━━


def check_metadata_match(
    doc_metadata: Optional[Dict[str, Any]], metadata_filter: Optional[Dict[str, Any]]
) -> bool:
    """
    문서의 메타데이터가 필터 조건에 부합하는지 확인합니다.

    Args:
        doc_metadata: 문서에서 추출한 메타데이터 딕셔너리
        metadata_filter: 적용할 필터 조건 (예: {"category": "Projects", "tags": ["AI", "Tech"]})

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
        doc_value = doc_metadata.get(filter_key)

        # 양쪽 값을 모두 리스트로 정규화하여 처리하되, None은 유효 값 매칭에서 제외
        filter_raw = filter_value if isinstance(filter_value, list) else [filter_value]
        doc_raw = doc_value if isinstance(doc_value, list) else [doc_value]

        # None이 아닌 실제 값들만 추출하여 비교 (필터링의 의도는 '실제 값'의 일치여야 함)
        filter_values = [v for v in filter_raw if v is not None]
        doc_values = [v for v in doc_raw if v is not None]

        # 만약 필터에 유효한 값이 명시되었는데 문서 값이 없거나 불일치하면 False
        if filter_values:
            if not doc_values or not any(v in filter_values for v in doc_values):
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
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


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
        import pypdf

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
