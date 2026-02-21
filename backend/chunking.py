# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/chunking.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - 텍스트 청킹
"""


import logging
from typing import Any, Optional, Dict, List

from langchain_text_splitters import TextSplitter, RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


class TextChunker:
    """텍스트를 작은 청크로 분할 (Langchain 기반, 다양한 스플리터 주입 지원)"""

    def __init__(
        self, splitter: Optional[TextSplitter] = None, **splitter_kwargs: Any
    ) -> None:
        """
        초기화
        - splitter를 주입하여 다양한 청킹 전략과 옵션을 지원합니다.
        - 파라미터를 중복 저장하지 않고 읽기 전용 프로퍼티로 관리하여 동기화 오류를 방지합니다.

        Args:
            splitter: 의존성 주입을 위한 TextSplitter 객체
            **splitter_kwargs: splitter가 없을 경우 생성할 RecursiveCharacterTextSplitter의 옵션값들
        """
        if splitter is not None:
            if not isinstance(splitter, TextSplitter):
                raise TypeError(
                    f"splitter must be an instance of TextSplitter, got {type(splitter).__name__}"
                )
            self._splitter = splitter
        else:
            chunk_size = splitter_kwargs.pop("chunk_size", 500)
            chunk_overlap = splitter_kwargs.pop("chunk_overlap", 50)

            self._splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size, chunk_overlap=chunk_overlap, **splitter_kwargs
            )

    @property
    def chunk_size(self) -> int:
        """현재 적용된 스플리터의 chunk_size 반환 (읽기 전용)"""
        return getattr(self._splitter, "_chunk_size", 0)

    @property
    def chunk_overlap(self) -> int:
        """현재 적용된 스플리터의 chunk_overlap 반환 (읽기 전용)"""
        return getattr(self._splitter, "_chunk_overlap", 0)

    def chunk_text(self, text: str) -> List[str]:
        """텍스트를 청크 단위로 분할"""
        if not text:
            return []

        # 입력 데이터 검증 (방어적 코딩)
        if not isinstance(text, str):
            logger.error(
                "Invalid text type for chunking",
                extra={"context": {"type": type(text).__name__}},
            )
            raise TypeError(f"text must be of type str, got {type(text).__name__}")

        return self._splitter.split_text(text)

    def chunk_with_metadata(
        self, text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """메타데이터와 함께 청크 생성"""
        chunks = self.chunk_text(text)

        # 메타데이터 타입 검증
        if metadata is not None and not isinstance(metadata, dict):
            logger.error(
                "Invalid metadata type",
                extra={"context": {"type": type(metadata).__name__}},
            )
            raise TypeError(
                f"metadata must be a dictionary, got {type(metadata).__name__}"
            )

        meta = metadata or {}

        return [
            {
                "text": chunk,
                "metadata": meta,
                "chunk_index": i,
                "total_chunks": len(chunks),
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
