# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/embedding.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - Embedding Generator Module (임베딩 생성).

[KO] 텍스트 청크를 입력받아 외부 API(OpenAI 등)를 호출하여 임베딩 벡터로 변환하는 모듈입니다.
[EN] Provides a class that takes text chunks and calls external APIs to convert them into embedding vectors.
"""

import types
from typing import Any, Dict, List, Mapping, Tuple, Type

from openai import APIConnectionError, APIError, APITimeoutError, RateLimitError

# from backend.config import get_embedding_model, EMBEDDING_MODEL, EMBEDDING_COSTS
from backend.config import EMBEDDING_COSTS, EMBEDDING_MODEL, ModelConfig
from backend.exceptions import EmbeddingError, EmbeddingErrorType
from backend.utils import count_tokens, estimate_cost

# 기본 예외 튜플 (Single Source of Truth)
DEFAULT_API_ERROR: Tuple[str, EmbeddingErrorType] = ("Embedding API error", "api_error")

# 예외 클래스에 따른 에러 메시지 접두사와 관측성 타입을 매핑하는 모듈 상수
# 런타임 불변성을 보장하기 위해 MappingProxyType 사용
ERROR_MAP: Mapping[Type[Exception], Tuple[str, EmbeddingErrorType]] = (
    types.MappingProxyType(
        {
            APITimeoutError: ("Embedding API call timed out", "timeout"),
            APIConnectionError: ("Embedding API connection error", "connection"),
            RateLimitError: ("Embedding API rate limit exceeded", "rate_limit"),
            APIError: DEFAULT_API_ERROR,
        }
    )
)


def _get_error_mapping(exc: Exception) -> Tuple[str, EmbeddingErrorType]:
    """주어진 예외 인스턴스에 가장 적합한 에러 메시지 접두사와 타입을 반환합니다."""
    return next(
        (v for k, v in ERROR_MAP.items() if isinstance(exc, k)),
        ERROR_MAP.get(APIError, DEFAULT_API_ERROR),
    )


class EmbeddingGenerator:
    """
    [KO] 임베딩 생성을 담당하는 제너레이터 클래스.
    [EN] Generator class responsible for creating embeddings.
    """

    def __init__(self, model_name: str = EMBEDDING_MODEL):
        self.model_name = model_name
        # self.client = get_embedding_model(model_name)
        self.client = ModelConfig.get_embedding_model(model_name)
        self.cost_per_token = EMBEDDING_COSTS.get(
            model_name.split("/")[-1], 0.02 / 1_000_000
        )  # ?

    def generate_embeddings(self, texts: List[str]) -> Dict[str, Any]:
        """
        [KO]
        텍스트 리스트에 대한 임베딩 벡터를 생성하고 비용 및 토큰 수를 반환합니다.

        Args:
            texts: 임베딩으로 변환할 텍스트 청크 리스트.

        Returns:
            임베딩 벡터 리스트, 총 사용 토큰 수, 예상 비용을 포함한 딕셔너리.

        Raises:
            EmbeddingError: 외부 임베딩 모델 API 호출에 실패한 경우 (HTTP 502 매핑 대상).

        [EN]
        Generates embedding vectors for a list of texts and returns cost and token metrics.

        Args:
            texts: List of text chunks to convert into embeddings.

        Returns:
            Dictionary containing embedding vectors, total token count, and estimated cost.

        Raises:
            EmbeddingError: If the external embedding model API call fails (mapped to HTTP 502).
        """
        if not texts:
            return {"embeddings": [], "tokens": 0, "cost": 0.0}

        # 토큰 수 계산
        total_tokens = sum(count_tokens(text) for text in texts)
        estimated_cost = estimate_cost(total_tokens, self.cost_per_token)

        try:
            # 임베딩 생성 API 호출
            # [NOTE] 이곳에서 통신 실패, Rate Limit 초과 등 외부 API 장애가 발생할 수 있습니다.
            # OpenAI SDK 전용 예외(APIError 계열)만 래핑하여, 내부 코드 버그(TypeError 등)가 마스킹되지 않도록 합니다.
            response = self.client.embeddings.create(model=self.model_name, input=texts)
        except (APITimeoutError, APIConnectionError, RateLimitError, APIError) as e:
            msg_prefix, err_type = _get_error_mapping(e)

            raise EmbeddingError(f"{msg_prefix}: {str(e)}", error_type=err_type) from e

        embeddings = [item.embedding for item in response.data]

        return {
            "embeddings": embeddings,
            "tokens": total_tokens,
            "cost": estimated_cost,
        }


if __name__ == "__main__":
    generator = EmbeddingGenerator()

    test_texts = [
        "FlowNote는 AI 대화 관리 도구입니다.",
        "대화 내용을 검색하고 분석할 수 있습니다.",
        "마크다운으로 대화를 내보낼 수 있습니다.",
    ]

    print("=" * 50)
    print("임베딩 테스트")
    print("=" * 50)
    print(f"\n📊 임베딩 생성 중... ({len(test_texts)}개 청크)")

    result = generator.generate_embeddings(test_texts)

    print("✅ 임베딩 완료!")
    print(f"   - 청크 수: {len(result['embeddings'])}")
    print(f"   - 토큰 수: {result['tokens']}")
    print(f"   - 예상 비용: ${result['cost']:.6f}")
    print(f"   - 벡터 차원: {len(result['embeddings'][0])}")

    print("\n" + "=" * 50)


"""result_2

    - 실행 방법_1: 프로젝트 루트에서 실행 시
        python -m backend.embedding

    - 실행 방법_2:
        python -m backend.faiss_search

    ==================================================
    임베딩 테스트
    ==================================================

    📊 임베딩 생성 중... (3개 청크)
    ✅ 임베딩 완료!
        - 청크 수: 3
        - 토큰 수: 48
        - 예상 비용: $0.000001
        - 벡터 차원: 1536

    ==================================================

"""


"""result_3

    ==================================================
    임베딩 테스트
    ==================================================

    📊 임베딩 생성 중... (3개 청크)
    ✅ 임베딩 완료!
        - 청크 수: 3
        - 토큰 수: 48
        - 예상 비용: $0.000001
        - 벡터 차원: 1536

    ==================================================

"""


"""result_4 - 클래스형 + 함수형 config.py 수정 후

    ==================================================
    임베딩 테스트
    ==================================================

    📊 임베딩 생성 중... (3개 청크)
    ✅ 임베딩 완료!
        - 청크 수: 3
        - 토큰 수: 48
        - 예상 비용: $0.000001
        - 벡터 차원: 1536

    ==================================================

"""
