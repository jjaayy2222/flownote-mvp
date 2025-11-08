# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/modules/pdf_helper.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - PDF 처리 모듈
"""

import pypdf
from typing import Union
from pathlib import Path

def extract_text_from_pdf(file) -> str:
    """
    PDF 파일에서 텍스트 추출 (Streamlit UploadedFile 또는 파일 경로)
    
    Args:
        file: Streamlit UploadedFile 객체 또는 파일 경로
    
    Returns:
        str: 추출된 텍스트
    """
    try:
        # UploadedFile인 경우
        if hasattr(file, 'read'):
            pdf_reader = pypdf.PdfReader(file)
        else:
            # 파일 경로인 경우
            pdf_reader = pypdf.PdfReader(str(file))
        
        text = ""
        for page_num, page in enumerate(pdf_reader.pages):
            try:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            except Exception as e:
                print(f"⚠️ Page {page_num+1} extraction failed: {e}")
                continue
        
        return text.strip()
    
    except Exception as e:
        raise Exception(f"PDF 읽기 실패: {str(e)}")


def is_valid_pdf(file) -> bool:
    """
    PDF 파일이 유효한지 확인
    
    Args:
        file: PDF 파일 객체
    
    Returns:
        bool: 유효하면 True
    """
    try:
        pdf_reader = pypdf.PdfReader(file)
        # 최소 1페이지 이상 있는지 확인
        return len(pdf_reader.pages) > 0
    except Exception:
        return False
