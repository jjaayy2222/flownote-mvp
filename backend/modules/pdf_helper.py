# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/modules/pdf_helper.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
[KO] FlowNote MVP - PDF 처리 모듈
[EN] FlowNote MVP - PDF Helper Module

[KO] 업로드된 PDF 파일에서 텍스트를 추출하거나 유효성을 검증하는 헬퍼 모듈입니다.
[EN] Helper module for extracting text or validating uploaded PDF files.
"""

import logging

from pypdf import PdfReader
from pypdf.errors import PyPdfError

logger = logging.getLogger(__name__)


def extract_text_from_pdf(file) -> str:
    """
    [KO]
    PDF 파일에서 텍스트를 추출합니다.

    Args:
        file: Streamlit UploadedFile 객체 또는 파일 경로

    Returns:
        추출된 전체 텍스트

    Raises:
        RuntimeError: PDF 읽기 실패 시 발생
            (예외 유형 포함: ``PDF 읽기 실패: ExcType: 메시지`` 형식으로 디버깅 지원)

    [EN]
    Extracts text from a PDF file.

    Args:
        file: Streamlit UploadedFile object or file path

    Returns:
        The complete text extracted from the PDF

    Raises:
        RuntimeError: Raised when PDF reading fails.
            Format: ``PDF 읽기 실패: ExcType: message``
            (note: the ``PDF 읽기 실패`` prefix is Korean-localized)
    """
    try:
        # UploadedFile인 경우
        if hasattr(file, "read"):
            pdf_reader = PdfReader(file)
        else:
            # 파일 경로인 경우
            pdf_reader = PdfReader(str(file))

        text = ""
        for page_num, page in enumerate(pdf_reader.pages):
            try:
                if page_text := page.extract_text():
                    text += page_text + "\n"
            except (PyPdfError, ValueError, OSError) as e:
                logger.warning(
                    "PDF page text extraction failed",
                    extra={
                        "page": page_num + 1,
                        "error_type": type(e).__name__,
                    },
                    exc_info=e,
                )
                continue

        return text.strip()

    except (PyPdfError, ValueError, OSError) as e:
        # PDF 파싱 오류(PyPdfError), 잘못된 입력값(ValueError), 또는 I/O 오류(OSError)
        raise RuntimeError(f"PDF 읽기 실패: {type(e).__name__}: {e}") from e


def is_valid_pdf(file) -> bool:
    """
    [KO]
    PDF 파일이 유효한지 확인합니다.

    Args:
        file: PDF 파일 객체 (Streamlit UploadedFile 또는 파일 경로)

    Returns:
        최소 1페이지 이상 존재하고 파싱 가능한 경우 True, 그렇지 않으면 False

    [EN]
    Validates if a PDF file is readable.

    Args:
        file: PDF file object (Streamlit UploadedFile or file path)

    Returns:
        True if the PDF has at least 1 page and can be parsed, False otherwise
    """
    try:
        pdf_reader = PdfReader(file)
        # 최소 1페이지 이상 있는지 확인
        return len(pdf_reader.pages) > 0
    except (PyPdfError, ValueError, OSError):
        return False
