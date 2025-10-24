# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/chunking.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote 텍스트 청킹
"""

from typing import List

def chunk_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 100
) -> List[str]:
    """
    텍스트를 청크로 분할
    
    Args:
        text: 분할할 텍스트
        chunk_size: 청크 크기 (기본: 500자)
        chunk_overlap: 겹치는 크기 (기본: 100자)
        
    Returns:
        List[str]: 청크 리스트
        
    Example:
        >>> text = "긴 글..." * 100
        >>> chunks = chunk_text(text)
        >>> len(chunks)
        5
    """
    if not text or not text.strip():
        return []
    
    chunks = []
    start = 0
    text_length = len(text)
    
    while start < text_length:
        # 끝 위치 계산
        end = start + chunk_size
        
        # 마지막 청크 처리
        if end >= text_length:
            chunks.append(text[start:])
            break
        
        # 청크 추출
        chunk = text[start:end]
        chunks.append(chunk)
        
        # 다음 시작 위치 (overlap 적용)
        start += (chunk_size - chunk_overlap)
    
    return chunks


def chunk_with_metadata(
    text: str,
    filename: str,
    chunk_size: int = 500,
    chunk_overlap: int = 100
) -> List[dict]:
    """
    청크 + 메타데이터
    
    Args:
        text: 분할할 텍스트
        filename: 파일명
        chunk_size: 청크 크기
        chunk_overlap: 겹침 크기
        
    Returns:
        List[dict]: 청크 + 메타데이터 리스트
        
    Example:
        >>> chunks = chunk_with_metadata(text, "chat.md")
        >>> chunks[0]
        {
            'text': '청크 내용...',
            'filename': 'chat.md',
            'chunk_id': 0,
            'start_pos': 0,
            'end_pos': 500
        }
    """
    chunks = chunk_text(text, chunk_size, chunk_overlap)
    
    result = []
    position = 0
    
    for idx, chunk in enumerate(chunks):
        metadata = {
            'text': chunk,
            'filename': filename,
            'chunk_id': idx,
            'start_pos': position,
            'end_pos': position + len(chunk)
        }
        result.append(metadata)
        position += (chunk_size - chunk_overlap)
    
    return result


# 사용 예시 (테스트용)
if __name__ == "__main__":
    # 테스트 텍스트
    test_text = """
    FlowNote는 AI 대화를 체계적으로 저장하고 검색하는 도구입니다.
    사용자는 AI와의 대화 내용을 파일로 업로드하고,
    키워드로 검색하여 필요한 정보를 빠르게 찾을 수 있습니다.
    """ * 10
    
    # 청킹
    chunks = chunk_text(test_text, chunk_size=100, chunk_overlap=20)
    
    print(f"총 청크 수: {len(chunks)}")
    print(f"\n첫 번째 청크:\n{chunks[0]}")
    print(f"\n두 번째 청크:\n{chunks[1]}")
    
    # 메타데이터 포함
    chunks_meta = chunk_with_metadata(test_text, "test.md", 100, 20)
    print(f"\n메타데이터:\n{chunks_meta[0]}")


"""result

    총 청크 수: 15

    첫 번째 청크:

        FlowNote는 AI 대화를 체계적으로 저장하고 검색하는 도구입니다.
        사용자는 AI와의 대화 내용을 파일로 업로드하고,
        키워드로 검색하여 필요한 정보를 빠

    두 번째 청크:
    키워드로 검색하여 필요한 정보를 빠르게 찾을 수 있습니다.
        
        FlowNote는 AI 대화를 체계적으로 저장하고 검색하는 도구입니다.
        사용자는 AI와의 대화 

    메타데이터:
    {'text': '\n    FlowNote는 AI 대화를 체계적으로 저장하고 검색하는 도구입니다.\n    사용자는 AI와의 대화 내용을 파일로 업로드하고,\n    키워드로 검색하여 필요한 정보를 빠', 
    'filename': 'test.md', 
    'chunk_id': 0, 
    'start_pos': 0, 
    'end_pos': 100}

"""