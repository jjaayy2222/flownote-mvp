# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/chunking.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - 텍스트 청킹
"""


class TextChunker:
    """텍스트를 작은 청크로 분할"""
    
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def chunk_text(self, text: str) -> list[str]:
        """텍스트를 청크로 분할"""
        if not text:
            return []
        
        chunks = []
        start = 0
        text_length = len(text)
        
        while start < text_length:
            end = start + self.chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start = end - self.chunk_overlap
        
        return chunks
    
    def chunk_with_metadata(self, text: str, metadata: dict = None) -> list[dict]:
        """메타데이터와 함께 청크 생성"""
        chunks = self.chunk_text(text)
        
        return [
            {
                "text": chunk,
                "metadata": metadata or {},
                "chunk_index": i,
                "total_chunks": len(chunks)
            }
            for i, chunk in enumerate(chunks)
        ]


if __name__ == "__main__":
    chunker = TextChunker(chunk_size=100, chunk_overlap=20)
    
    test_text = "FlowNote는 AI 대화 관리 도구입니다. " * 10
    
    print("=" * 50)
    print("청킹 테스트")
    print("=" * 50)
    
    chunks = chunker.chunk_text(test_text)
    print(f"\n✅ 생성된 청크 수: {len(chunks)}")
    print(f"   - 첫 청크: {chunks[0][:50]}...")
    
    chunks_meta = chunker.chunk_with_metadata(test_text, {"source": "test"})
    print(f"\n✅ 메타데이터 포함 청크: {len(chunks_meta)}개")
    print(f"   - 첫 청크 정보: {chunks_meta[0]}")
    
    print("\n" + "=" * 50)




"""result_1 (수정 전)

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



"""result_2 (수정 후)

    ==================================================
    청킹 테스트
    ==================================================

    1. 기본 청킹 테스트
        - 청크 수: 6개
        - 첫 번째 청크: FlowNote는 AI 대화 관리 도구입니다. 
            이 도구는 대화 내용을 저장하고 검...

    2. 메타데이터 포함 청킹
        - 청크 수: 6개
        - 첫 번째 청크 정보:
            * 텍스트: FlowNote는 AI 대화 관리 도구입니다. 
            이 도구는 대화 내용을 저장하고 검...
            * 소스: test.md
            * 인덱스: 0/6

    ==================================================
    테스트 완료!

"""



"""result_3

    ==================================================
    청킹 테스트
    ==================================================

    ✅ 생성된 청크 수: 4
        - 첫 청크: FlowNote는 AI 대화 관리 도구입니다. FlowNote는 AI 대화 관리 도구입니다...

    ✅ 메타데이터 포함 청크: 4개
        - 첫 청크 정보: {'text': 'FlowNote는 AI 대화 관리 도구입니다. FlowNote는 AI 대화 관리 도구입니다. FlowNote는 AI 대화 관리 도구입니다. FlowNote는 AI 대화 관리 도구입', 'metadata': {'source': 'test'}, 'chunk_index': 0, 'total_chunks': 4}

    ==================================================

"""