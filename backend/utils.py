# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/utils.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - 유틸리티 함수
"""

import os
import tiktoken
from pathlib import Path
from typing import Optional
from datetime import datetime

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
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        raise Exception(f"파일 읽기 실패: {str(e)}")


def format_file_size(size_bytes: int) -> str:
    """파일 크기를 읽기 쉬운 형식으로 변환"""
    for unit in ['B', 'KB', 'MB', 'GB']:
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
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"# {title}\n\n")
        f.write(f"생성일: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("---\n\n")
        f.write(text)
