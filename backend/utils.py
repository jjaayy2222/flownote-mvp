#━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/utils.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote 유틸리티 함수
"""

from pathlib import Path
from datetime import datetime
from typing import List

def get_timestamp():
    """
    현재 시간 문자열 반환 (YYYY-MM-DD_HH-MM-SS)
    
    Returns:
        str: 타임스탬프 문자열
    """
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def read_file(file_path: Path) -> str:
    """
    파일 읽기 (UTF-8)
    
    Args:
        file_path: 파일 경로
        
    Returns:
        str: 파일 내용
    """
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

def save_file(content: str, file_path: Path):
    """
    파일 저장 (UTF-8)
    
    Args:
        content: 저장할 내용
        file_path: 파일 경로
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> List[str]:
    """
    텍스트를 청크로 분할
    
    Args:
        text: 분할할 텍스트
        chunk_size: 청크 크기 (기본: 500자)
        overlap: 겹치는 크기 (기본: 100자)
        
    Returns:
        List[str]: 청크 리스트
    """
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start += (chunk_size - overlap)
    
    return chunks

def format_file_size(size_bytes: int) -> str:
    """
    파일 크기를 읽기 쉬운 형식으로 변환
    
    Args:
        size_bytes: 바이트 단위 크기
        
    Returns:
        str: 포맷된 크기 (예: "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"

def validate_file_extension(filename: str, allowed_extensions: List[str]) -> bool:
    """
    파일 확장자 검증
    
    Args:
        filename: 파일명
        allowed_extensions: 허용된 확장자 리스트 (예: ['.md', '.txt'])
        
    Returns:
        bool: 허용 여부
    """
    file_path = Path(filename)
    return file_path.suffix.lower() in allowed_extensions