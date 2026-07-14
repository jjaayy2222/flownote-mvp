# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/embedding.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
[KO] FlowNote MVP - 임베딩 생성 모듈
[EN] FlowNote MVP - Embedding Generator Module

[KO] 텍스트 청크를 입력받아 외부 API(OpenAI 등)를 호출하여 임베딩 벡터로 변환하는 모듈입니다.
[EN] Provides a class that takes text chunks and calls external APIs to convert them into embedding vectors.
"""

import types
from typing import List, Mapping, Tuple, Type, TypedDict

from openai import APIConnectionError, APIError, APITimeoutError, RateLimitError

# from backend.config import get_embedding_model, EMBEDDING_MODEL, EMBEDDING_COSTS
from backend.config import EMBEDDING_COSTS, EMBEDDING_MODEL, ModelConfig
from backend.exceptions import ConfigurationError, EmbeddingError, EmbeddingErrorType
from backend.utils import count_tokens, estimate_cost

# 기본 예외 튜플 (Single Source of Truth)
# [KO] API 오류 발생 시 반환할 기본 메시지와 에러 타입
# [EN] Default message and error type returned upon API error
DEFAULT_API_ERROR: Tuple[str, EmbeddingErrorType] = ("Embedding API error", "api_error")


class EmbeddingResult(TypedDict):
    """
    [KO] 임베딩 생성 결과 반환 타입
    [EN] Return type for embedding generation results
    """

    embeddings: List[List[float]]
    tokens: int
    cost: float


# 예외 클래스에 따른 에러 메시지 접두사와 관측성 타입을 매핑하는 모듈 상수
# 런타임 불변성을 보장하기 위해 MappingProxyType 사용
# [KO] OpenAI API 예외별로 적절한 메시지 접두어와 내부 에러 타입을 매핑한 딕셔너리
# [EN] Dictionary mapping specific OpenAI API exceptions to message prefixes and internal error types
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


def _verify_invariants() -> None:
    """
    [KO] 모듈 내 불변 조건(Invariant)을 검증하는 부트스트랩 함수입니다.
         런타임에 안전한지 초기화 단계에서 명시적으로 확인합니다.
    [EN] Bootstrap function that verifies invariants within the module.
         Explicitly checks for runtime safety during the initialization phase.

    Raises:
        ConfigurationError: [KO] `APIError` 매핑이 `DEFAULT_API_ERROR`와 일치하지 않을 때 발생합니다.
                            / [EN] Raised when `APIError` mapping does not match `DEFAULT_API_ERROR`.
    """
    if ERROR_MAP.get(APIError) != DEFAULT_API_ERROR:
        raise ConfigurationError("APIError mapping must match DEFAULT_API_ERROR")


def _get_error_mapping(exc: Exception) -> Tuple[str, EmbeddingErrorType]:
    """
    [KO] 주어진 예외 인스턴스에 가장 적합한 에러 메시지 접두사와 타입을 반환합니다.
    [EN] Returns the most appropriate error message prefix and type for a given exception instance.

    Args:
        exc (Exception): [KO] 발생한 예외 객체 / [EN] The exception object that was raised

    Returns:
        Tuple[str, EmbeddingErrorType]: [KO] 메시지 접두어와 에러 타입을 포함하는 튜플
                                        / [EN] A tuple containing the message prefix and error type
    """
    return next(
        (v for k, v in ERROR_MAP.items() if isinstance(exc, k)),
        DEFAULT_API_ERROR,
    )


class EmbeddingGenerator:
    """
    [KO] 텍스트 임베딩 생성을 담당하는 제너레이터 클래스입니다.
    [EN] Generator class responsible for creating text embeddings.
    """

    def __init__(self, model_name: str = EMBEDDING_MODEL):
        """
        [KO] 사용할 임베딩 모델을 설정하고 API 클라이언트를 초기화합니다.
        [EN] Sets the embedding model to use and initializes the API client.

        Args:
            model_name (str): [KO] 사용할 임베딩 모델의 이름 (기본값: EMBEDDING_MODEL)
                              / [EN] Name of the embedding model to use (default: EMBEDDING_MODEL)
        """
        _verify_invariants()
        self.model_name = model_name
        # self.client = get_embedding_model(model_name)
        self.client = ModelConfig.get_embedding_model(model_name)
        self.cost_per_token = EMBEDDING_COSTS.get(
            model_name.split("/")[-1], 0.02 / 1_000_000
        )  # ?

    def generate_embeddings(self, texts: List[str]) -> EmbeddingResult:
        """
        [KO] 텍스트 리스트에 대한 임베딩 벡터를 생성하고 비용 및 토큰 수를 반환합니다.
        [EN] Generates embedding vectors for a list of texts and returns cost and token metrics.

        Args:
            texts (List[str]): [KO] 임베딩으로 변환할 텍스트 청크 리스트
                               / [EN] List of text chunks to convert into embeddings.

        Returns:
            EmbeddingResult: [KO] 임베딩 벡터 리스트, 총 사용 토큰 수, 예상 비용을 포함한 딕셔너리
                            / [EN] Dictionary containing embedding vectors, total token count, and estimated cost.

        Raises:
            EmbeddingError: [KO] 외부 임베딩 모델 API 호출에 실패한 경우 (HTTP 502 매핑 대상)
                            / [EN] If the external embedding model API call fails (mapped to HTTP 502).
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
