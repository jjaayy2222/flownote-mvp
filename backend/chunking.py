# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/chunking.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - 텍스트 청킹
"""


import logging
from typing import Any, Optional, Dict, List, Set, Tuple

from langchain_text_splitters import TextSplitter, RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


class TextChunker:
    """텍스트를 작은 청크로 분할 (Langchain 기반, 선택적 스플리터 주입)"""

    def __init__(
        self,
        splitter: Optional[TextSplitter] = None,
        *,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        **splitter_kwargs: Any,
    ) -> None:
        """
        초기화
        - splitter를 주입하거나 기본 RecursiveCharacterTextSplitter를 사용합니다.
        - 고급 설정이 필요한 경우 splitter_kwargs를 통해 RecursiveCharacterTextSplitter 옵션을 전달할 수 있습니다.

        Args:
            splitter: 의존성 주입을 위한 TextSplitter 객체
            chunk_size: 청크 크기 (기본 스플리터 사용 시)
            chunk_overlap: 청크 중첩 크기 (기본 스플리터 사용 시)
            splitter_kwargs: (고급) 기본 RecursiveCharacterTextSplitter에 전달할 추가 옵션들
        """
        if splitter is not None:
            if not isinstance(splitter, TextSplitter):
                raise TypeError(
                    f"splitter must be an instance of TextSplitter, got {type(splitter).__name__}"
                )
            self._splitter = splitter
        else:
            # 중복 키워드 인자 충돌 방지 (방어적 코딩)
            kwargs = dict(splitter_kwargs)
            kwargs.pop("chunk_size", None)
            kwargs.pop("chunk_overlap", None)

            self._splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size, chunk_overlap=chunk_overlap, **kwargs
            )

        self._warned_missing_attrs: Set[Tuple[int, str, str, str]] = set()

    MAX_INVALID_VALUE_REPR_LEN: int = 100

    def _get_splitter_context(self) -> Dict[str, Any]:
        return {
            "splitter_id": id(self._splitter),
            "splitter_type": type(self._splitter).__name__,
        }

    def _coerce_splitter_int_attr(
        self, attr_name: str, *, is_private: bool = False
    ) -> Optional[int]:
        if not hasattr(self._splitter, attr_name):
            return None

        val = getattr(self._splitter, attr_name)
        if val is None:
            return None
        if isinstance(val, int) and not isinstance(val, bool):
            return val

        try:
            return int(val)  # type: ignore[arg-type]
        except (ValueError, TypeError):
            val_repr = repr(val)
            max_len = self.MAX_INVALID_VALUE_REPR_LEN
            safe_val = (
                val_repr[:max_len] + "..." if len(val_repr) > max_len else val_repr
            )

            context = self._get_splitter_context()
            context.update(
                {
                    "invalid_type": type(val).__name__,
                    "invalid_value": safe_val,
                    "private_attr" if is_private else "attr_name": attr_name,
                }
            )

            logger.warning(
                f"Attribute '{attr_name}' on {context['splitter_type']} is not a valid int",
                extra={"context": context},
            )
            return None

    def _log_missing_splitter_attr(self, attr_name: str, private_attr: str) -> None:
        context = self._get_splitter_context()
        missing_attr_key = (
            context["splitter_id"],
            context["splitter_type"],
            attr_name,
            private_attr,
        )
        if missing_attr_key in self._warned_missing_attrs:
            return

        context.update(
            {
                "attr_name": attr_name,
                "private_attr": private_attr,
            }
        )

        logger.info(
            f"Could not find '{attr_name}' or '{private_attr}' on {context['splitter_type']}",
            extra={"context": context},
        )
        self._warned_missing_attrs.add(missing_attr_key)

    def _get_splitter_attr(
        self, attr_name: str, fallback_attr: Optional[str] = None
    ) -> Optional[int]:
        """스플리터에서 동적으로 속성을 읽어옵니다 (Public 및 명시적 Fallback 속성 지원)."""
        # 1. Public 속성 시도
        val = self._coerce_splitter_int_attr(attr_name, is_private=False)
        if val is not None:
            return val

        # 2. Private/Fallback 속성 시도
        private_attr = fallback_attr or f"_{attr_name}"
        val = self._coerce_splitter_int_attr(private_attr, is_private=True)
        if val is not None:
            return val

        # 3. 양쪽 모두 없을 경우, 중복 로깅 방지 후 info 레벨로 기록 (침묵 회피)
        self._log_missing_splitter_attr(attr_name, private_attr)
        return None

    @property
    def chunk_size(self) -> Optional[int]:
        """현재 스플리터에 설정된 chunk_size 동적 반환 (런타임 변경 반영)"""
        return self._get_splitter_attr("chunk_size")

    @property
    def chunk_overlap(self) -> Optional[int]:
        """현재 스플리터에 설정된 chunk_overlap 동적 반환 (런타임 변경 반영)"""
        return self._get_splitter_attr("chunk_overlap")

    def chunk_text(self, text: str) -> List[str]:
        """텍스트를 청크 단위로 분할"""
        if not isinstance(text, str):
            logger.error(
                "Invalid text type for chunking",
                extra={"context": {"type": type(text).__name__}},
            )
            raise TypeError(f"text must be of type str, got {type(text).__name__}")
        if not text:
            return []

        return self._splitter.split_text(text)

    def chunk_with_metadata(
        self, text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """메타데이터와 함께 청크 생성"""
        if metadata is not None and not isinstance(metadata, dict):
            logger.error(
                "Invalid metadata type",
                extra={"context": {"type": type(metadata).__name__}},
            )
            raise TypeError(
                f"metadata must be a dictionary, got {type(metadata).__name__}"
            )

        chunks = self.chunk_text(text)
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
