# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/utils.py (수정)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - 유틸리티 함수 (파일 처리 포함)
"""

import os
import tiktoken
from pathlib import Path
from typing import Optional

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# PDF 처리 라이브러리 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━
try:
    import pypdf as PyPDF2          # pypdf를 PyPDF2 이름으로 사용
    PDF_AVAILABLE = True            # PyPDF2 라이브러리 가용성 확인
except ImportError:
    PDF_AVAILABLE = False           # PyPDF2 라이브러리 미가용

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True     # pdfplumber 라이브러리 가용성 확인
except ImportError:
    PDFPLUMBER_AVAILABLE = False    # pdfplumber 라이브러리 미가용

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 인코딩 감지 라이브러리
# ━━━━━━━━━━━━━━━━━━━━━━━━━━
try:
    import chardet
    CHARDET_AVAILABLE = True        # chardet 라이브러리 가용성 확인
except ImportError:
    CHARDET_AVAILABLE = False       # chardet 라이브러리 미가용


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 기존 함수들
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

def count_tokens(text: str, model: str = "gpt-4") -> int:
    """
    텍스트의 토큰 수 계산
    
    Args:
        text: 토큰을 계산할 텍스트 입력
        model: 사용할 모델 이름 (기본: gpt-4)
    
    Returns:
        토큰 수 반환
    """
    try:
        # 모델별 인코딩 객체 획득
        encoding = tiktoken.encoding_for_model(model) 
    except KeyError:
        # 모델을 찾을 수 없으면 cl100k_base 사용
        encoding = tiktoken.get_encoding("cl100k_base")     # 기본 인코딩 설정
    
    # 인코딩된 토큰 리스트 길이 반환
    return len(encoding.encode(text)) 


def estimate_cost(tokens: int, cost_per_token: float) -> float:
    """
    토큰 수를 기반으로 비용 추정
    
    Args:
        tokens: 토큰 수 입력
        cost_per_token: 토큰당 비용 입력
    
    Returns:
        추정 비용 (USD) 반환
    """
    
    # 비용 계산 및 반환
    return tokens * cost_per_token 

def format_file_size(size_bytes: int) -> str:
    """
    파일 크기를 읽기 쉬운 형식으로 변환 (B, KB, MB, GB)
    
    Args:
        size_bytes: 바이트 단위 크기 입력
    
    Returns:
        포맷된 크기 문자열 반환 (예: "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB']: 
        # 크기 단위 순회
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"           # 1024 미만 시 포맷 반환
        size_bytes /= 1024.0                            # 1024 이상 시 단위 변환
    
    # 최종적으로 TB 단위 반환
    return f"{size_bytes:.1f} TB" 


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 새로운 파일 처리 함수들
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

def read_file_content(file_path: str) -> Optional[str]:
    """
    파일 내용 읽기 통합 함수 (TXT, PDF, MD 지원)
    
    Args:
        file_path: 파일 경로 입력
    
    Returns:
        파일 내용 (문자열) 또는 None 반환
    """
    try:
        # 파일 확장자 추출
        file_ext = Path(file_path).suffix.lower() 
        
        # PDF 처리
        if file_ext == '.pdf':
            # PDF 파일 읽기 함수 호출
            return read_pdf_file(file_path) 
        
        # MD/TXT 처리
        elif file_ext in ['.md', '.txt']:
            # 텍스트 파일 읽기 함수 호출
            return read_text_file(file_path) 
        
        else:
            # 지원하지 않는 형식 예외 처리
            raise ValueError(f"지원하지 않는 파일 형식 오류: {file_ext}") 
    
    except Exception as e:
        # 파일 읽기 중 발생한 기타 오류 처리
        print(f"❌ 파일 읽기 오류 ({file_path}): {str(e)}") 
        return None                             # 오류 발생 시 None 반환


def read_pdf_file(file_path: str) -> str:
    """
    PDF 파일 읽기 전용 함수
    
    Args:
        file_path: PDF 파일 경로 입력
    
    Returns:
        추출된 텍스트 반환
        
    Raises:
        ValueError: PDF 처리 실패 시 예외 발생
    """
    text = ""
    
    # 1순위: pdfplumber 사용 시도 (더 정확함)
    if PDFPLUMBER_AVAILABLE:
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"            # 페이지 텍스트 누적
                        print(f"✅ PDF 페이지 {page_num} 처리 완료")
            
            if text.strip():
                print(f"✅ pdfplumber로 PDF 처리 성공: {len(text)} 문자")
                return text                                 # 텍스트 추출 성공 시 반환
            else:
                print("⚠️ pdfplumber로 텍스트를 추출하지 못했습니다.")      # 추출 실패 경고
                
        except Exception as e:
            print(f"⚠️ pdfplumber 오류: {str(e)}")                   # pdfplumber 처리 오류
    
    # 2순위: PyPDF2 사용 시도 (fallback)
    if PDF_AVAILABLE and not text.strip():
        try:
            import pypdf as PyPDF2                                  # pypdf를 PyPDF2 이름으로 사용
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                num_pages = len(reader.pages)
                
                for page_num, page in enumerate(reader.pages, 1):
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"                    # 페이지 텍스트 누적
                        print(f"✅ PDF 페이지 {page_num}/{num_pages} 처리 완료")
            
            if text.strip():
                print(f"✅ PyPDF2로 PDF 처리 성공: {len(text)} 문자")
                return text                                         # 텍스트 추출 성공 시 반환
            else:
                print("⚠️ PyPDF2로 텍스트를 추출하지 못했습니다.")          # 추출 실패 경고
                
        except Exception as e:
            print(f"⚠️ PyPDF2 오류: {str(e)}")                       # PyPDF2 처리 오류
    
    # 둘 다 실패 처리
    if not text.strip():
        if not PDF_AVAILABLE and not PDFPLUMBER_AVAILABLE:
            raise ValueError(
                "❌ PDF 처리 라이브러리 미설치 오류"
            )
        else:
            raise ValueError(
                f"❌ PDF 파일 텍스트 추출 실패: {file_path}"
            )
    
    # 최종 텍스트 반환
    return text 


def read_text_file(file_path: str) -> str:
    """
    텍스트 파일 읽기 전용 함수 (TXT, MD)
    
    Args:
        file_path: 파일 경로 입력
    
    Returns:
        파일 내용 반환
        
    Raises:
        ValueError: 인코딩 실패 시 예외 발생
    """
    # chardet 사용 가능 시 자동 인코딩 감지 시도
    if CHARDET_AVAILABLE:
        try:
            with open(file_path, 'rb') as f:
                raw_data = f.read()                         # 파일의 원본 바이트 데이터 읽기
                result = chardet.detect(raw_data)           # 인코딩 감지
                detected_encoding = result['encoding']
                confidence = result['confidence']
                
                print(f"✅ 인코딩 감지: {detected_encoding} (신뢰도: {confidence:.2%})")
                
                if detected_encoding and confidence > 0.7:
                    try:
                        # 감지된 인코딩으로 디코딩
                        content = raw_data.decode(detected_encoding) 
                        if content.strip():
                            print(f"✅ {detected_encoding}으로 파일 읽기 성공")
                            return content                  # 성공 시 내용 반환
                    except (UnicodeDecodeError, LookupError):
                        # 디코딩 오류 시 경고
                        print(f"⚠️ {detected_encoding} 디코딩 실패, 다른 인코딩 시도") 
        except Exception as e:
            # chardet 실행 오류 시 경고
            print(f"⚠️ chardet 오류: {str(e)}") 
    
    # chardet 실패 또는 없을 시 순차 인코딩 시도
    # 시도할 인코딩 리스트
    encodings = ['utf-8', 'cp949', 'euc-kr', 'latin-1', 'utf-16'] 
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()                          # 파일 내용 읽기
                if content.strip():
                    print(f"✅ {encoding}으로 파일 읽기 성공")
                    return content                          # 성공 시 내용 반환
        except (UnicodeDecodeError, LookupError):
            continue                                        # 디코딩 실패 시 다음 인코딩 시도
        except Exception as e:
            print(f"⚠️ {encoding} 읽기 오류: {str(e)}")       # 기타 읽기 오류 처리
            continue
    
    raise ValueError(
        f"❌ 파일 인코딩 인식 실패 오류: {file_path}"
    )                                                       # 모든 인코딩 시도 실패 시 예외 발생


def detect_encoding(file_path: str) -> str:
    """
    파일 인코딩 자동 감지 함수
    
    Args:
        file_path: 파일 경로 입력
    
    Returns:
        감지된 인코딩 반환 (기본값: 'utf-8')
    """
    if not CHARDET_AVAILABLE:
        return 'utf-8'                                      # 라이브러리 없으면 기본값 반환
    
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read()                             # 원본 바이트 데이터 읽기
            result = chardet.detect(raw_data)               # 인코딩 감지
            encoding = result['encoding']
            confidence = result['confidence']
            
            if encoding and confidence > 0.7:
                return encoding                             # 신뢰도 높은 인코딩 반환
    except Exception:
        pass                                                # 오류 발생 시 무시
    
    return 'utf-8'                                          # 최종 기본값 반환


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 테스트 코드
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    # 기존 함수 테스트
    test_text = "FlowNote는 AI 대화 관리 도구입니다."
    tokens = count_tokens(test_text)
    cost = estimate_cost(tokens, 0.02 / 1_000_000)
    
    print("=" * 50)
    print("유틸리티 함수 테스트")
    print("=" * 50)
    print(f"\n텍스트: {test_text}")
    print(f"토큰 수: {tokens}")
    print(f"예상 비용: ${cost:.6f}")
    print(f"파일 크기 예시: {format_file_size(1536)}")
    print("\n" + "=" * 50)
    
    # 라이브러리 가용성 확인
    print("\n라이브러리 가용성:")
    print(f"  - pdfplumber: {'✅ 사용 가능' if PDFPLUMBER_AVAILABLE else '❌ 없음'}")
    print(f"  - PyPDF2: {'✅ 사용 가능' if PDF_AVAILABLE else '❌ 없음'}")
    print(f"  - chardet: {'✅ 사용 가능' if CHARDET_AVAILABLE else '❌ 없음'}")
    print("=" * 50)



"""result_2

    ==================================================
    유틸리티 함수 테스트
    ==================================================

    텍스트: FlowNote는 AI 대화 관리 도구입니다.
    토큰 수: 13
    예상 비용: $0.000000
    파일 크기 예시: 1.5 KB

    ==================================================

"""



"""result_3

    ==================================================
    유틸리티 함수 테스트
    ==================================================

    텍스트: FlowNote는 AI 대화 관리 도구입니다.
    토큰 수: 13
    예상 비용: $0.000000
    파일 크기 예시: 1.5 KB

    ==================================================

    라이브러리 가용성:
        - pdfplumber: ✅ 사용 가능
        - PyPDF2: ✅ 사용 가능
        - chardet: ✅ 사용 가능
    ==================================================

"""