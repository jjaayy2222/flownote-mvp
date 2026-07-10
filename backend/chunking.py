# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/chunking.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
[KO] FlowNote MVP - 텍스트 청킹(Text Chunking) 모듈
[EN] FlowNote MVP - Text Chunking module
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from langchain_text_splitters import RecursiveCharacterTextSplitter, TextSplitter

logger = logging.getLogger(__name__)


class TextChunker:
    """
    [KO] 텍스트를 작은 청크로 분할하는 클래스입니다. (Langchain 기반, 의존성 주입 지원)
    [EN] A class to split text into smaller chunks. (Based on Langchain, supports dependency injection)
    """

    def __init__(
        self,
        splitter: Optional[TextSplitter] = None,
        *,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        **splitter_kwargs: Any,
    ) -> None:
        """
        [KO] 초기화: splitter를 주입하거나 기본 RecursiveCharacterTextSplitter를 사용합니다.
        [EN] Initialization: Injects a splitter or uses the default RecursiveCharacterTextSplitter.

        Args:
            splitter (Optional[TextSplitter]): 의존성 주입을 위한 TextSplitter 객체 / TextSplitter object for dependency injection
            chunk_size (int): 청크 크기 (기본 스플리터 사용 시) / Chunk size (when using default splitter)
            chunk_overlap (int): 청크 중첩 크기 (기본 스플리터 사용 시) / Chunk overlap size (when using default splitter)
            **splitter_kwargs: 기본 스플리터에 전달할 추가 옵션 / Additional options to pass to the default splitter
        """
        if splitter is None:
            # 중복 키워드 인자 충돌 방지 (방어적 코딩)
            kwargs = dict(splitter_kwargs)
            kwargs.pop("chunk_size", None)
            kwargs.pop("chunk_overlap", None)

            self._splitter: TextSplitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size, chunk_overlap=chunk_overlap, **kwargs
            )
        elif not isinstance(splitter, TextSplitter):
            raise TypeError(
                f"splitter must be an instance of TextSplitter, got {type(splitter).__name__}"
            )
        else:
            self._splitter = splitter

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
            self._log_invalid_int_attr(val, attr_name, is_private)
            return None

    def _log_invalid_int_attr(self, val: Any, attr_name: str, is_private: bool) -> None:
        """유효하지 않은 int 속성 값을 안전하게 로깅합니다."""
        val_repr = repr(val)
        max_len = self.MAX_INVALID_VALUE_REPR_LEN
        safe_val = f"{val_repr[:max_len]}..." if len(val_repr) > max_len else val_repr

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
        """
        [KO] 스플리터에서 동적으로 속성을 읽어옵니다. (Public 및 명시적 Fallback 속성 지원)
        [EN] Dynamically reads an attribute from the splitter. (Supports Public and explicit Fallback attributes)
        """
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
        """
        [KO] 현재 스플리터에 설정된 chunk_size 동적 반환 (런타임 변경 반영)
        [EN] Dynamically returns the chunk_size set on the current splitter (reflects runtime changes)
        """
        return self._get_splitter_attr("chunk_size")

    @property
    def chunk_overlap(self) -> Optional[int]:
        """
        [KO] 현재 스플리터에 설정된 chunk_overlap 동적 반환 (런타임 변경 반영)
        [EN] Dynamically returns the chunk_overlap set on the current splitter (reflects runtime changes)
        """
        return self._get_splitter_attr("chunk_overlap")

    def chunk_text(self, text: str) -> List[str]:
        """
        [KO] 텍스트를 청크 단위로 분할합니다.
        [EN] Splits text into chunks.

        Args:
            text (str): 분할할 텍스트 / The text to split
        Returns:
            List[str]: 분할된 문자열 청크 리스트 / List of string chunks
        Raises:
            TypeError: text가 str 타입이 아닌 경우 / If text is not a string type
        """
        if not isinstance(text, str):
            logger.error(
                "Invalid text type for chunking",
                extra={"context": {"type": type(text).__name__}},
            )
            raise TypeError(f"text must be of type str, got {type(text).__name__}")
        if not text:
            empty_chunks: List[str] = []
            return empty_chunks

        return self._splitter.split_text(text)

    def chunk_with_metadata(
        self, text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        [KO] 메타데이터와 함께 텍스트 청크를 생성합니다.
        [EN] Generates text chunks along with metadata.

        Args:
            text (str): 분할할 원본 텍스트 / The original text to split
            metadata (Optional[Dict[str, Any]]): 각 청크에 포함할 메타데이터 / Metadata to include in each chunk
        Returns:
            List[Dict[str, Any]]: 텍스트와 메타데이터가 결합된 청크 리스트 / List of chunks combined with text and metadata
        Raises:
            TypeError: metadata가 딕셔너리 타입이 아닌 경우 / If metadata is not a dictionary type
        """
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
