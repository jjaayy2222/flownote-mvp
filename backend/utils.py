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

        # 1. 필터값이 리스트인 경우 (OR 조건: 필터 리스트 중 하나라도 일치하면 OK)
        if isinstance(filter_value, list):
            if isinstance(doc_value, list):
                # 리스트 vs 리스트: 교집합이 있는지 확인 (하나라도 겹치면 매칭)
                # set() 변환은 dict 등 해시 불가능한 요소가 있을 경우 실패하므로 순회 방식으로 체크
                match_found = False
                for item in doc_value:
                    if item in filter_value:
                        match_found = True
                        break
                if not match_found:
                    return False
            else:
                # 스칼라 vs 리스트: 필터 리스트에 포함되는지 확인
                if doc_value not in filter_value:
                    return False

        # 2. 필터값이 스칼라인 경우 (일치 조건)
        else:
            if isinstance(doc_value, list):
                # 리스트 vs 스칼라: 문서 리스트 내에 필터값이 포함되는지 확인
                if filter_value not in doc_value:
                    return False
            else:
                # 스칼라 vs 스칼라: 단순 값 비교
                if doc_value != filter_value:
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
