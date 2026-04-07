# backend/services/eval_service.py

"""
[v8.0] Phase 5 - Step 2: '싫어요(Thumbs Down)' 원인 분석 프레임워크

'싫어요' 피드백을 받은 AI 응답의 실패 원인을 자동으로 분류합니다.
- RAG Retrieval Failure: 검색된 단락 자체가 질문과 무관한 경우
- Hallucination: 검색 단락에 없는 내용을 LLM이 생성한 경우

[Step 2-2 설계 결정 - 외부 평가 라이브러리 연동 검토 결과]
외부 라이브러리(Ragas)는 다음 이유로 미적용 결정:
  1. 의존성 충돌 위험: ragas 설치 시 langchain-core 강제 업그레이드 + scipy·huggingface_hub 등
     대규모 패키지 추가로 기존 운영 환경 안정성 훼손 우려.
  2. 비용 중복: Ragas의 faithfulness·context_recall 지표도 내부적으로 LLM을 호출하므로,
     이미 구현된 자체 평가 프롬프트(_build_eval_prompt)와 기능이 중복되어 API 비용만 배가됨.
대신 자체 LLM 판별 프롬프트(classify_negative_feedback)를 기본 전략으로 유지하고,
배치 파이프라인에 EVAL_SAMPLING_RATE 기반 샘플링 전략을 추가하여 비용을 제어합니다.

관련 이슈: #934
브랜치: feature/issue-934-eval-framework
"""

import json
import logging
import os
import random
import re
from collections import OrderedDict, Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from json import JSONDecodeError
from typing import Any, AsyncIterator, Literal, Optional

import redis.exceptions

from backend.services.chat_history_service import (  # type: ignore[import]
    FEEDBACK_KEY_PREFIX,
    _HISTORY_PREFIX,
)
from backend.services.redis_pubsub import redis_client  # type: ignore[import]
from backend.utils import mask_pii_id  # type: ignore[import]

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Redis 키 상수
# ─────────────────────────────────────────────────────────────

# RAG 컨텍스트 저장 키: chat:rag_context:{session_id} (Hash)
# field: message_id, value: JSON {"retrieved_docs": [...], "query": "...", "timestamp": "..."}
_RAG_CONTEXT_PREFIX = "chat:rag_context:"

# 평가 결과 저장 키: chat:eval:{session_id} (Hash)
# field: message_id, value: JSON EvalResult 직렬화
_EVAL_RESULT_PREFIX = "chat:eval:"

# Redis TTL: 7일 (chat_history_service와 동일하게 맞춤)
_DEFAULT_TTL = 86400 * 7

# 분류 판별에 사용할 LLM 모델 (환경 변수로 오버라이드 가능)
_DEFAULT_EVAL_MODEL = "gpt-4o-mini"

# 평가 프롬프트에 포함할 retrieved_docs 상한 (환경변수 오버라이드 가능)
# 기본값 10개 / 2000자는 gpt-4o-mini 128k 컨텍스트 기준으로 안전한 상한입니다.
_DEFAULT_MAX_EVAL_DOCS = 10
_DEFAULT_MAX_EVAL_DOC_CHARS = 2000

# 세션별 history 스캔 상한: 가장 최신 N개 메시지만 조회하여 lrange 비용 통제
# 기본값 200: assistant/user 교대 기준으로 최대 100회 도리(람에) 추적 가능
_DEFAULT_EVAL_HISTORY_SCAN_LIMIT = 200
# 안전 상한(Hard Cap): 설정 오류로 인한 과도한 Redis LRANGE 방지
# 환경변수 값이 이 값을 초과하면 경고 로그 후 이 값으로 클램프
_MAX_EVAL_HISTORY_SCAN_LIMIT = 4000

# 배치 파이프라인 내 session_history_cache 최대 세션 수
# 이 크기를 초과하면 캐시를 비워 메모리 스파이크를 방지합니다.
_MAX_SESSION_HISTORY_CACHE_SIZE = 500

# [Step 2-2] 샘플링 전략 상수
# EVAL_SAMPLING_RATE: 전체 '싫어요' 피드백 중 평가를 수행할 비율 (0.0 초과 ~ 1.0 이하)
# 기본값 1.0 = 전체 평가. 예: 0.2 = 20%만 샘플링하여 OpenAI API 비용 절감.
# 환경변수 EVAL_SAMPLING_RATE로 오버라이드 가능. 범위 벗어나면 기본값 1.0으로 복원.
_DEFAULT_EVAL_SAMPLING_RATE = 1.0

# OpenAI API 키 조회 우선순위 (단일 진실 공급원 SSOT)
# 이 공통 상수를 수정하면 조회 로직에러 메시지가 자동으로 동기화됩니다.
OPENAI_API_KEY_ENV_VARS: tuple[str, ...] = (
    "GPT4O_MINI_API_KEY",
    "GPT4O_API_KEY",
    "OPENAI_API_KEY",
)

# OpenAI Base URL 조회 우선순위
OPENAI_BASE_URL_ENV_VARS: tuple[str, ...] = (
    "GPT4O_MINI_BASE_URL",
    "GPT4O_BASE_URL",
    "OPENAI_BASE_URL",
)

# EvalLabel: 분류 결과 리터럴 타입
EvalLabel = Literal["hallucination", "rag_retrieval_failure", "uncertain"]


# ─────────────────────────────────────────────────────────────
# 데이터 구조체
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EvalResult:
    """
    단일 AI 응답에 대한 원인 분석 결과.

    frozen=True: 불변(Immutable) 보장. set/dict key 안전 사용 가능.

    Attributes:
        session_id:   세션 식별자 (원본 보존; 외부 노출 시 mask_pii_id 필수)
        message_id:   해당 AI 응답의 메시지 식별자
        label:        분류 결과 - 'hallucination' | 'rag_retrieval_failure' | 'uncertain'
        reason:       LLM이 생성한 분류 근거 설명 (한국어)
        eval_model:   분류에 사용된 LLM 모델명
        rag_query:    RAG 검색 시 사용된 원본 질의 (없을 경우 None)
        timestamp:    평가 수행 시각 (ISO 8601 UTC)
    """

    session_id: str
    message_id: str
    label: EvalLabel
    reason: str
    eval_model: str
    rag_query: Optional[str]
    timestamp: str


# ─────────────────────────────────────────────────────────────
# 모듈 레벨 순수 헬퍼 함수
# ─────────────────────────────────────────────────────────────


def _now_utc_iso() -> str:
    """현재 UTC 시각을 ISO 8601 형식 문자열로 반환하는 중앙 헬퍼."""
    return datetime.now(timezone.utc).isoformat()


def _get_eval_model() -> str:
    """환경 변수에서 평가 모델을 읽어 반환. 미설정 시 기본값 사용."""
    return os.environ.get("EVAL_LLM_MODEL", _DEFAULT_EVAL_MODEL).strip() or _DEFAULT_EVAL_MODEL


def _get_max_eval_docs() -> int:
    """프롬프트에 포함할 최대 문서 개수를 환경 변수에서 읽어 반환."""
    try:
        val = int(os.environ.get("EVAL_MAX_RETRIEVED_DOCS", str(_DEFAULT_MAX_EVAL_DOCS)))
        return val if val > 0 else _DEFAULT_MAX_EVAL_DOCS
    except ValueError:
        return _DEFAULT_MAX_EVAL_DOCS


def _get_max_eval_doc_chars() -> int:
    """프롬프트에 포함할 문서 1개의 최대 문자 수를 환경 변수에서 읽어 반환."""
    try:
        val = int(os.environ.get("EVAL_MAX_RETRIEVED_DOC_CHARS", str(_DEFAULT_MAX_EVAL_DOC_CHARS)))
        return val if val > 0 else _DEFAULT_MAX_EVAL_DOC_CHARS
    except ValueError:
        return _DEFAULT_MAX_EVAL_DOC_CHARS


def _get_eval_history_scan_limit() -> int:
    """
    세션별 history를 조회할 최대 메시지 수를 환경 변수에서 읽어 반환.

    _MAX_EVAL_HISTORY_SCAN_LIMIT로 클램프하여 설정 오류 시에도
    과도한 Redis LRANGE 호출이 발생하지 않도록 보호합니다.
    """
    try:
        val = int(os.environ.get("EVAL_HISTORY_SCAN_LIMIT", str(_DEFAULT_EVAL_HISTORY_SCAN_LIMIT)))
        limit = val if val > 0 else _DEFAULT_EVAL_HISTORY_SCAN_LIMIT
    except ValueError:
        return _DEFAULT_EVAL_HISTORY_SCAN_LIMIT

    # 안전 상한 클램프: 비정상적으로 큰 값으로 인한 Redis OOM 방지
    if limit > _MAX_EVAL_HISTORY_SCAN_LIMIT:
        logger.warning(
            "[OBS] EVAL_HISTORY_SCAN_LIMIT=%s exceeds max=%s; clamping to max. "
            "Check your environment configuration.",
            limit,
            _MAX_EVAL_HISTORY_SCAN_LIMIT,
        )
        limit = _MAX_EVAL_HISTORY_SCAN_LIMIT
    return limit


def _get_eval_sampling_rate() -> float:
    """
    [Step 2-2] 배치 파이프라인에서 평가를 수행할 샘플링 비율을 환경 변수에서 읽어 반환.

    EVAL_SAMPLING_RATE 환경변수로 제어하며, 유효 범위는 (0.0, 1.0] 입니다.
    - 기본값 1.0 = 전체 평가 (기존 동작과 동일).
    - 예: 0.2 → '싫어요' 피드백 중 무작위 20%만 LLM 평가하여 API 비용 절감.
    - 범위를 벗어난 값(0 이하 또는 1 초과, 숫자가 아닌 값)은 기본값 1.0으로 복원하고 경고 로그를 남깁니다.

    Note: Ragas 미적용 대안으로 도입된 비용 제어 전략입니다. (Step 2-2 설계 결정 참조)
    """
    raw = os.environ.get("EVAL_SAMPLING_RATE", str(_DEFAULT_EVAL_SAMPLING_RATE))
    try:
        rate = float(raw)
    except ValueError:
        logger.warning(
            "[OBS] EVAL_SAMPLING_RATE='%s' is not a valid float; using default=%.1f.",
            raw,
            _DEFAULT_EVAL_SAMPLING_RATE,
        )
        return _DEFAULT_EVAL_SAMPLING_RATE

    # [SSOT] 범위 검증을 공통 헬퍼에 위임 (중복 로직 제거)
    return _validate_sampling_rate(rate, "EVAL_SAMPLING_RATE env")


def _validate_sampling_rate(rate: float, source: str) -> float:
    """
    [SSOT] sampling_rate 범위 검증 로직의 단일 진실 공급원.

    유효 범위: (0.0, 1.0]. 범위 벗어난 값은 기본값으로 복원하고 경고 로그를 기록.
    ‘_get_eval_sampling_rate()’(환경변수 경로)와
    ‘run_negative_feedback_eval_pipeline’(명시적 인자 경로) 모두에서
    호출하여 검증 로직과 로그 메시지가 한 곳에서 일관되게 유지되도록 합니다.

    Args:
        rate:   검증할 부동소수점 비율.
        source: 에러 로그에 표시할 키 출처 ("EVAL_SAMPLING_RATE env" 또는 "explicit arg" 등).

    Returns:
        유효한 비율 값 또는 복원된 기본값 (_DEFAULT_EVAL_SAMPLING_RATE).
    """
    if not (0.0 < rate <= 1.0):
        logger.warning(
            "[OBS] sampling_rate=%.4f from '%s' is out of range (0.0, 1.0]; "
            "using default=%.1f.",
            rate,
            source,
            _DEFAULT_EVAL_SAMPLING_RATE,
        )
        return _DEFAULT_EVAL_SAMPLING_RATE
    return rate


# ─────────────────────────────────────────────────────────────
# LRU 세션 히스토리 캐시
# ─────────────────────────────────────────────────────────────


class _SessionHistoryCache:
    """
    배치 평가 파이프라인용 LRU 기반 세션 히스토리 캐시.

    동일 세션의 여러 피드백에 대해 Redis lrange를 1회만 수행하도록
    세션별 히스토리를 인메모리에 캐싱합니다.

    캐시 크기가 max_size를 초과할 때 가장 오래된(가장 덜 사용된) 세션을 자동으로
    퇴출합니다 (LRU Eviction Policy).

    [Design Decision]
    - 인라인으로 펼치는 대신 클래스로 분리하여 로직 커플링 방지
    - 비즈니스 로직(Redis 조회)을 담당하는 파이프라인 함수는 캐시 구조를 모르면 됨
    - get()/put() API로 캐시 상호작용을 명확히 표현
    """

    def __init__(self, max_size: int) -> None:
        self._cache: OrderedDict[str, list[dict]] = OrderedDict()
        self._max_size = max_size

    def get(self, session_id: str) -> Optional[list[dict]]:
        """
        세션 히스토리를 조회합니다.

        캐시에 존재하면 LRU 순위를 갱신(move_to_end)하고 히스토리를 반환합니다.
        존재하지 않으면 None을 반환합니다.
        """
        if session_id not in self._cache:
            return None
        self._cache.move_to_end(session_id)
        return self._cache[session_id]

    def put(self, session_id: str, history: list[dict]) -> Optional[str]:
        """
        세션 히스토리를 캐시에 저장합니다.

        이미 존재하는 session_id인 경우 덮어쓰고 LRU 순위만 갱신합니다.
        (퇴출 없음 - 기존 세션 업데이트는 캐시 크기를 변경하지 않으므로)

        신규 session_id인 경우 max_size 초과 시 LRU 세션을 퇴출하고
        퇴출된 session_id를 반환합니다. 퇴출이 없으면 None을 반환합니다.

        [Atomicity]
        퇴출과 삽입을 단일 메서드에서 처리하여, 호출자는 캐시 내부 동작을 신경 쓰지 않아도 됩니다.
        """
        # [Bug Fix] 이미 존재하는 세션이면 덮어쓰고 LRU 순위만 갱신 (불필요한 퇴출 방지)
        if session_id in self._cache:
            self._cache[session_id] = history
            self._cache.move_to_end(session_id)
            return None

        evicted: Optional[str] = None
        if len(self._cache) >= self._max_size:
            evicted_id, _ = self._cache.popitem(last=False)
            evicted = evicted_id
        self._cache[session_id] = history
        return evicted

    def __len__(self) -> int:
        return len(self._cache)


def _get_api_key_from_env() -> str:
    """
    OpenAI 계열 모델 호출에 사용할 API 키를 환경 변수에서 조회합니다.
    조회 우선순위: GPT4O_MINI_API_KEY → GPT4O_API_KEY → OPENAI_API_KEY

    OPENAI_API_KEY_ENV_VARS 상수를 단일 진실 공급원(SSOT)으로 사용하여
    조회 로직과 에러 메시지가 항상 일치하도록 보장합니다.

    Note: 반환된 API 키는 절대 로그에 출력하지 않습니다 (Secret 보호).
    """
    for var_name in OPENAI_API_KEY_ENV_VARS:
        value = os.getenv(var_name)
        if value:
            return value
    raise ValueError(
        f"OpenAI API key is missing. Please set one of: {', '.join(OPENAI_API_KEY_ENV_VARS)}."
    )


def _get_base_url_from_env() -> Optional[str]:
    """OpenAI base URL을 환경 변수에서 조회합니다. 설정되지 않으면 None 반환."""
    for var_name in OPENAI_BASE_URL_ENV_VARS:
        value = os.getenv(var_name)
        if value:
            return value
    return None


@lru_cache(maxsize=4)
def _get_eval_llm(model: str, api_key: str, base_url: Optional[str]):
    """
    ChatOpenAI 평가 클라이언트를 (model, api_key, base_url) 조합 기준으로 캐싱합니다.

    [Engineering Decision - Performance]
    배치 파이프라인에서 수백~수천 건을 분류할 때 매 호출마다 새 인스턴스를 생성하면
    소켓 설정·키 검증 오버헤드가 선형으로 증가합니다.
    lru_cache(maxsize=4)로 환경 변수 조합별 클라이언트를 재사용하여 오버헤드를 제거합니다.

    Note: api_key를 캐시 키로 사용하지만 로그에는 절대 출력하지 않습니다 (PII/Secret 보호).
    """
    from langchain_openai import ChatOpenAI  # type: ignore[import]

    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        streaming=False,
        temperature=0.0,  # 분류 작업: 결정론적 응답이 최적
    )


def _build_eval_prompt(query: str, retrieved_docs: list[str], ai_response: str) -> str:
    """
    RAG vs Hallucination 판별을 위한 평가 프롬프트 생성.

    프롬프트는 명확한 구조(3섹션)로 구성하여 LLM 응답 정확도를 최대화합니다.
    한국어 응답을 요청하여 관리자 보고서 가독성을 높입니다.
    """
    docs_text = "\n\n".join(
        f"[문서 {i+1}]\n{doc}" for i, doc in enumerate(retrieved_docs)
    ) if retrieved_docs else "(검색된 문서 없음)"

    return f"""당신은 AI 응답의 품질을 평가하는 전문 평가자입니다.
아래의 세 가지 정보를 분석하여, AI 응답 실패의 근본 원인을 분류해주세요.

---
[사용자 질문]
{query}

---
[RAG 검색으로 가져온 참고 문서]
{docs_text}

---
[AI가 최종 생성한 응답]
{ai_response}

---
[분류 지침]
1. **hallucination**: AI 응답에 참고 문서에 없는 내용이 포함된 경우 (AI가 사실을 지어냄)
2. **rag_retrieval_failure**: 참고 문서 자체가 사용자 질문과 무관하여 답변에 도움이 안 된 경우
3. **uncertain**: 위 두 경우를 명확히 구분하기 어려운 경우

반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 절대 포함하지 마세요:
{{
  "label": "hallucination" | "rag_retrieval_failure" | "uncertain",
  "reason": "분류 근거를 한국어 1~2문장으로 설명"
}}"""


def _parse_eval_response(response_text: str) -> tuple[EvalLabel, str]:
    """
    LLM 평가 응답 텍스트를 파싱하여 (label, reason) 튜플로 반환.

    파싱 실패 시 'uncertain'으로 폴백하여 파이프라인이 중단되지 않도록 합니다.
    """
    valid_labels: set[str] = {"hallucination", "rag_retrieval_failure", "uncertain"}

    try:
        # JSON 응답에서 코드 블록 마커(```json ... ```) 제거
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        cleaned = cleaned.strip()

        parsed = json.loads(cleaned)
        label = str(parsed.get("label", "uncertain")).strip()
        reason = str(parsed.get("reason", "분류 근거를 파악할 수 없습니다.")).strip()

        if label not in valid_labels:
            logger.warning(
                "[OBS] Eval LLM returned an unrecognized label; falling back to 'uncertain'.",
                extra={"received_label": label[:50]},
            )
            label = "uncertain"

        return label, reason  # type: ignore[return-value]

    except (JSONDecodeError, ValueError, AttributeError) as e:
        logger.warning(
            "[OBS] Failed to parse eval LLM response JSON; falling back to 'uncertain'.",
            extra={"error": str(e), "response_preview": response_text[:200]},
        )
        return "uncertain", "LLM 응답 파싱에 실패하여 자동으로 'uncertain'으로 분류되었습니다."


# ─────────────────────────────────────────────────────────────
# RAG 컨텍스트 저장 함수 (chat_service 연동용)
# ─────────────────────────────────────────────────────────────


async def save_rag_context(
    session_id: str,
    message_id: str,
    query: str,
    retrieved_docs: list[str],
    *,
    ttl: int = _DEFAULT_TTL,
) -> None:
    """
    RAG 검색 결과(retrieved_docs)와 질의를 Redis에 저장합니다.
    chat_service의 stream_chat 완료 시점에 호출되어,
    Step 2의 평가 파이프라인이 검색 문서를 참조할 수 있게 합니다.

    Redis 키 구조:
        chat:rag_context:{session_id}  (Hash)
        field: message_id
        value: JSON {"query": "...", "retrieved_docs": [...], "timestamp": "..."}

    Args:
        session_id:    세션 식별자
        message_id:    message_id (chat_history의 assistant 메시지 ID와 연계)
        query:         RAG 검색에 사용된 사용자 질의
        retrieved_docs: 검색된 문서 내용 리스트 (page_content 기준)
        ttl:           Redis 키 만료 시간 (초, 기본값: 7일)
    """
    if not session_id or not message_id:
        logger.warning(
            "[OBS] save_rag_context called with empty session_id or message_id; skipping.",
        )
        return

    try:
        if not redis_client.is_connected():
            await redis_client.connect()

        key = f"{_RAG_CONTEXT_PREFIX}{session_id}"
        payload = {
            "query": query,
            "retrieved_docs": retrieved_docs,
            "timestamp": _now_utc_iso(),
        }
        await redis_client.redis.hset(key, message_id, json.dumps(payload, ensure_ascii=False))
        await redis_client.redis.expire(key, ttl)

        logger.debug(
            "RAG context saved.",
            extra={
                "session_id_hash": mask_pii_id(session_id),
                "message_id_hash": mask_pii_id(message_id),
                "doc_count": len(retrieved_docs),
            },
        )

    except redis.exceptions.RedisError as e:
        # RAG 컨텍스트 저장 실패는 비치명적 오류: 로깅 후 조용히 무시
        # (메인 채팅 스트리밍 흐름을 방해하지 않습니다)
        logger.error(
            "[OBS] Failed to save RAG context to Redis; evaluation pipeline may be impacted.",
            extra={
                "session_id_hash": mask_pii_id(session_id),
                "error": str(e),
            },
        )


# ─────────────────────────────────────────────────────────────
# 핵심 평가 서비스 함수
# ─────────────────────────────────────────────────────────────


async def classify_negative_feedback(
    session_id: str,
    message_id: str,
    ai_response: str,
) -> Optional[EvalResult]:
    """
    단일 '싫어요' 응답에 대해 실패 원인을 LLM으로 분류하고
    EvalResult를 반환합니다.

    동작 흐름:
        1. Redis에서 해당 message_id의 RAG 컨텍스트(query + retrieved_docs)를 조회
        2. 평가 프롬프트 구성 (query + retrieved_docs + ai_response)
        3. LLM 호출 및 응답 파싱 (hallucination / rag_retrieval_failure / uncertain)
        4. EvalResult를 Redis에 저장하고 반환

    Args:
        session_id:   세션 식별자
        message_id:   '싫어요' 피드백이 달린 AI 응답의 message_id
        ai_response:  Redis chat:history에서 조회한 AI 응답 텍스트

    Returns:
        EvalResult 또는 처리 불가 시 None
    """
    if not session_id or not message_id or not ai_response.strip():
        logger.warning(
            "[OBS] classify_negative_feedback called with missing arguments; skipping.",
            extra={"session_id_hash": mask_pii_id(session_id)},
        )
        return None

    try:
        if not redis_client.is_connected():
            await redis_client.connect()

        # ── Step 1: RAG 컨텍스트 조회 ───────────────────────────────
        rag_key = f"{_RAG_CONTEXT_PREFIX}{session_id}"
        raw_context = await redis_client.redis.hget(rag_key, message_id)

        query = "(질의 정보 없음)"
        retrieved_docs: list[str] = []

        if raw_context:
            try:
                ctx_str = raw_context.decode("utf-8") if isinstance(raw_context, bytes) else str(raw_context)
                ctx = json.loads(ctx_str)
                query = ctx.get("query", query)
                raw_docs = ctx.get("retrieved_docs", [])

                # 안전한 타입 보장: 각 문서는 str로 캐스팅
                docs_as_str = [str(d) for d in raw_docs if d is not None]

                # 프롬프트 크기 제어: 개수 및 문자 수 상한 적용 (환경변수로 조정 가능)
                # 과도한 토큰으로 인한 API 오류 및 응답 지연을 사전에 방지합니다.
                max_docs = _get_max_eval_docs()
                max_chars = _get_max_eval_doc_chars()
                retrieved_docs = [
                    doc[:max_chars] for doc in docs_as_str[:max_docs]
                ]
            except (JSONDecodeError, ValueError, AttributeError) as e:
                logger.warning(
                    "[OBS] Failed to parse RAG context from Redis; proceeding with empty docs.",
                    extra={
                        "session_id_hash": mask_pii_id(session_id),
                        "message_id_hash": mask_pii_id(message_id),
                        "error": str(e),
                    },
                )
        else:
            logger.info(
                "[OBS] No RAG context found for this message; evaluation will proceed with empty retrieved_docs.",
                extra={
                    "session_id_hash": mask_pii_id(session_id),
                    "message_id_hash": mask_pii_id(message_id),
                },
            )

        # ── Step 2: 평가 프롬프트 구성 및 LLM 호출 ─────────────────
        eval_model = _get_eval_model()
        prompt_text = _build_eval_prompt(query, retrieved_docs, ai_response)

        # [Performance + SSOT] 캐시된 LLM 클라이언트 사용 + 공통 헬퍼로 API 키 조회
        api_key = _get_api_key_from_env()
        base_url = _get_base_url_from_env()
        eval_llm = _get_eval_llm(eval_model, api_key, base_url)

        from langchain_core.messages import HumanMessage  # type: ignore[import]

        llm_response = await eval_llm.ainvoke([HumanMessage(content=prompt_text)])
        response_text = str(llm_response.content).strip()

        # ── Step 3: LLM 응답 파싱 ───────────────────────────────────
        label, reason = _parse_eval_response(response_text)

        eval_result = EvalResult(
            session_id=session_id,
            message_id=message_id,
            label=label,
            reason=reason,
            eval_model=eval_model,
            rag_query=query if query != "(질의 정보 없음)" else None,
            timestamp=_now_utc_iso(),
        )

        # ── Step 4: 평가 결과 Redis 저장 ────────────────────────────
        eval_key = f"{_EVAL_RESULT_PREFIX}{session_id}"
        eval_payload = {
            "label": eval_result.label,
            "reason": eval_result.reason,
            "eval_model": eval_result.eval_model,
            "rag_query": eval_result.rag_query,
            "timestamp": eval_result.timestamp,
        }
        await redis_client.redis.hset(
            eval_key, message_id, json.dumps(eval_payload, ensure_ascii=False)
        )
        await redis_client.redis.expire(eval_key, _DEFAULT_TTL)

        logger.info(
            "[OBS] Eval classification complete.",
            extra={
                "session_id_hash": mask_pii_id(session_id),
                "message_id_hash": mask_pii_id(message_id),
                "label": label,
                "eval_model": eval_model,
                "retrieved_doc_count": len(retrieved_docs),
            },
        )

        return eval_result

    except redis.exceptions.RedisError as e:
        logger.error(
            "[OBS] Redis error during eval classification.",
            extra={"session_id_hash": mask_pii_id(session_id), "error": str(e)},
        )
        raise
    except ValueError as e:
        # API 키 누락 등 설정 오류: 상위 레이어로 전파
        logger.error(
            "[OBS] Configuration error during eval classification.",
            extra={"error": str(e)},
        )
        raise


async def run_negative_feedback_eval_pipeline(
    *,
    batch_size: int = 100,
    sampling_rate: Optional[float] = None,
) -> dict[str, Any]:
    """
    Redis의 모든 '싫어요' 피드백을 대상으로 분류 파이프라인을 실행합니다.
    이미 평가된 항목(chat:eval:* 키 존재)은 건너뛰어 중복 LLM 호출을 방지합니다.

    [Step 2-2 - 샘플링 전략]
    sampling_rate 인자 또는 EVAL_SAMPLING_RATE 환경변수(기본 1.0)로 평가 비율을 제어합니다.
    예: sampling_rate=0.2 → '싫어요' 중 무작위 20%만 LLM 분류하여 API 비용 절감.
    Ragas 미사용 시 자체 LLM 판별(classify_negative_feedback)이 기본 전략으로 동작합니다.

    Args:
        batch_size:     Redis SCAN 한 번에 반환할 최대 키 수.
        sampling_rate:  평가를 수행할 비율 (0.0 초과 ~ 1.0 이하).
                        None이면 EVAL_SAMPLING_RATE 환경변수에서 읽어옵니다.
                        명시적으로 전달하면 환경변수보다 우선합니다.
                        (테스트 시 환경변수 조작 없이 비율을 제어할 수 있습니다.)

    Returns:
        실행 요약 dict:
            {
                "total_negative": int,         # 전체 '싫어요' 피드백 수
                "sampled": int,                # 샘플링 후 평가 대상 수
                "sampling_rate": float,        # 적용된 샘플링 비율
                "classified": int,             # LLM 분류 성공 수
                "skipped_already_evaluated": int,
                "skipped_sampling": int,       # 샘플링으로 건너뛴 수
                "skipped_no_response": int,
                "errors": int,
                "label_counts": {"hallucination": int, "rag_retrieval_failure": int, "uncertain": int}
            }
    """
    # [DI] 명시적 인자가 제공되면 우선 사용, 아니면 환경변수에서 조회
    # 범위 검증은 _validate_sampling_rate() SSOT 헬퍼로 준수 (로직 중복 제거)
    if sampling_rate is None:
        sampling_rate = _get_eval_sampling_rate()
    else:
        sampling_rate = _validate_sampling_rate(sampling_rate, "explicit arg")
    summary: dict[str, Any] = {
        "total_negative": 0,
        "sampled": 0,
        "sampling_rate": sampling_rate,
        "classified": 0,
        "skipped_already_evaluated": 0,
        "skipped_sampling": 0,
        "skipped_no_response": 0,
        "errors": 0,
        "label_counts": {"hallucination": 0, "rag_retrieval_failure": 0, "uncertain": 0},
    }

    logger.info(
        "[OBS] Starting negative feedback eval pipeline.",
        extra={"sampling_rate": sampling_rate},
    )

    try:
        if not redis_client.is_connected():
            await redis_client.connect()

        # [Performance] 세션별 history LRU 캐시: 동일 session의 여러 피드백에 대해 lrange를 1회만 수행
        # _SessionHistoryCache로 커플링되어 파이프라인 함수는 캐시 내부 구조를 신경 쓰지 않아도 된다.
        history_cache = _SessionHistoryCache(max_size=_MAX_SESSION_HISTORY_CACHE_SIZE)
        history_scan_limit = _get_eval_history_scan_limit()

        cursor = 0
        while True:
            cursor, partial_keys = await redis_client.redis.scan(
                cursor, match=f"{FEEDBACK_KEY_PREFIX}*", count=batch_size
            )

            for raw_key in partial_keys:
                key_str = raw_key.decode("utf-8") if isinstance(raw_key, bytes) else str(raw_key)
                session_id = key_str.removeprefix(FEEDBACK_KEY_PREFIX)
                if not session_id:
                    continue

                feedback_hash = await redis_client.redis.hgetall(key_str)
                for msg_id_raw, meta_raw in feedback_hash.items():
                    msg_id = msg_id_raw.decode("utf-8") if isinstance(msg_id_raw, bytes) else str(msg_id_raw)

                    # rating 파싱 및 'down' 필터링
                    try:
                        meta_str = meta_raw.decode("utf-8") if isinstance(meta_raw, bytes) else str(meta_raw)
                        meta = json.loads(meta_str)
                    except (JSONDecodeError, ValueError):
                        continue

                    if meta.get("rating") != "down":
                        continue

                    summary["total_negative"] += 1

                    # 중복 평가 방지: 이미 결과가 있으면 건너뜀
                    eval_key = f"{_EVAL_RESULT_PREFIX}{session_id}"
                    existing = await redis_client.redis.hget(eval_key, msg_id)
                    if existing:
                        summary["skipped_already_evaluated"] += 1
                        continue

                    # [Step 2-2] 샘플링 전략: EVAL_SAMPLING_RATE 미만인 경우만 평가 진행
                    # sampling_rate == 1.0이면 random.random() < 1.0이 항상 True → 전체 평가
                    # sampling_rate == 0.2이면 약 20%만 평가하여 LLM API 비용 절감
                    if random.random() >= sampling_rate:
                        summary["skipped_sampling"] += 1
                        continue

                    summary["sampled"] += 1

                    # ── chat:history 조회 (_SessionHistoryCache LRU로 N×M Redis 호출 원천 차단) ──
                    # RAG context(chat:rag_context)가 존재하면 message_id로 정확히 매칭되지만,
                    # 없는 경우에도 최대한 정확한 assistant 메시지를 찾아야 합니다.
                    cached_history = history_cache.get(session_id)
                    if cached_history is None:
                        history_key = f"{_HISTORY_PREFIX}{session_id}"
                        # lrange 범위 제한: 최근 N개만 조회하여 메모리·속도 절약
                        history_raw = await redis_client.redis.lrange(
                            history_key, -history_scan_limit, -1
                        )
                        parsed: list[dict] = []
                        for item in history_raw:
                            try:
                                msg_dict = json.loads(
                                    item.decode("utf-8") if isinstance(item, bytes) else str(item)
                                )
                                if isinstance(msg_dict, dict):
                                    parsed.append(msg_dict)
                            except (JSONDecodeError, ValueError, AttributeError):
                                continue

                        history = list(reversed(parsed))  # 역순: 최신 메시지부터 탐색
                        evicted = history_cache.put(session_id, history)
                        if evicted:
                            # 로그: 퇴출 + 삽입이 모두 완료된 후의 실제 캐시 크기를 기록
                            logger.debug(
                                "[OBS] session_history_cache LRU eviction: removed oldest session "
                                "(evicted=%s, cache_size_after_insert=%s, max_size=%s).",
                                mask_pii_id(evicted),       # PII 안전 익명화
                                len(history_cache),         # 퇴출 + 삽입 후 실제 크기
                                _MAX_SESSION_HISTORY_CACHE_SIZE,
                            )
                        cached_history = history


                    # ── AI 응답 이중 매칭 전략 ────────────────────────────────
                    # 1순위: history 항목에 message_id 필드가 있다면 피드백 msg_id와 정확히 매칭
                    # 2순위: 정확 매칭 실패 시 가장 최신 assistant 응답으로 fallback
                    # (history에 message_id가 저장되어 있으면 1순위에서 반드시 매칭됩니다)
                    ai_response: Optional[str] = None
                    latest_assistant_response: Optional[str] = None

                    for msg_dict in cached_history:  # 이미 역순 정렬된 캐시
                        if msg_dict.get("role") != "assistant":
                            continue
                        content = msg_dict.get("content", "")
                        if not content or not str(content).strip():
                            continue

                        # 1순위: message_id 정확 매칭
                        if msg_dict.get("message_id") == msg_id:
                            ai_response = str(content)
                            break

                        # 2순위용 fallback 보관 (최신 assistant 메시지)
                        if latest_assistant_response is None:
                            latest_assistant_response = str(content)

                    # 정확 매칭 실패 시 최신 assistant 응답으로 fallback
                    if not ai_response and latest_assistant_response:
                        logger.debug(
                            # [Log Level: DEBUG]
                            # 배치 실행 중 message_id가 없는 기존 히스토리(배포 이전 저장분)에서
                            # 대량으로 발생할 수 있으므로, INFO 대신 DEBUG로 유지하여 로그 노이즈를 방지합니다.
                            # 운영 중 매칭 실패 추세를 모니터링하려면 배치 완료 요약 로그를 활용하세요.
                            "[OBS] message_id exact match failed; using latest assistant response as fallback.",
                            extra={
                                "session_id_hash": mask_pii_id(session_id),
                                "message_id_hash": mask_pii_id(msg_id),
                            },
                        )
                        ai_response = latest_assistant_response

                    if not ai_response:
                        summary["skipped_no_response"] += 1
                        continue

                    # 분류 실행
                    try:
                        result = await classify_negative_feedback(session_id, msg_id, ai_response)
                        if result:
                            summary["classified"] += 1
                            label_key = result.label
                            if label_key in summary["label_counts"]:
                                summary["label_counts"][label_key] += 1
                    except Exception as e:
                        summary["errors"] += 1
                        logger.error(
                            "[OBS] Error during individual eval classification; skipping item.",
                            extra={
                                "session_id_hash": mask_pii_id(session_id),
                                "message_id_hash": mask_pii_id(msg_id),
                                "error": str(e),
                            },
                        )

            if int(cursor) == 0:
                break

        # [Invariant Post-Check] 외부 불변식 검증 (False-Positive 제거 버전)
        #
        # 파이프라인 분기 트리는 total_negative가 정확히 3가의 배타적 경로로 소진됨:
        #   total_negative
        #   ├── skipped_already_evaluated  (중복 평가 방지, continue)
        #   ├── skipped_sampling            (샘플링 제외, continue)
        #   └── sampled                     (평가 진행 대상)
        #       └── (내부: classified, skipped_no_response, errors, None반환등 복합)
        #
        # classified/errors를 포함하면 classify_negative_feedback()가 None을 반환하는
        # 정상 경로를 눌리는 게산 오류로 거짓 경고 발생 가능.
        # 따라서 진정으로 배타적이고 전체를 포괄하는 외부 불물식만 사용.
        outer_sum = (
            summary["skipped_already_evaluated"]
            + summary["skipped_sampling"]
            + summary["sampled"]
        )
        if summary["total_negative"] != outer_sum:
            logger.warning(
                "[OBS] Pipeline summary invariant mismatch: "
                "total_negative=%d != (skipped_already_evaluated=%d + skipped_sampling=%d + sampled=%d). "
                "This may indicate a logic regression in the pipeline branching.",
                summary["total_negative"],
                summary["skipped_already_evaluated"],
                summary["skipped_sampling"],
                summary["sampled"],
            )

        logger.info(
            "[OBS] Negative feedback eval pipeline complete.",
            extra=summary,
        )
        return summary

    except redis.exceptions.RedisError as e:
        logger.error(
            "[OBS] Redis error during eval pipeline execution.",
            extra={"error": str(e)},
        )
        raise

# ─────────────────────────────────────────────────────────────
# 관리자 보고서(대시보드)용 키워드 클러스터링 및 통계 추출 로직
# ─────────────────────────────────────────────────────────────

# [Step 2-3] 관리자 보고서용 Redis SCAN 상한 (요청당 최대 반복 횟수)
# 환경변수 EVAL_REPORT_MAX_SCAN_ITERATIONS 로 조정 가능
_EVAL_REPORT_MAX_SCAN_ITERATIONS = max(1, int(os.getenv("EVAL_REPORT_MAX_SCAN_ITERATIONS", "100")))

# [Step 2-3] Redis SCAN 1회당 조회할 키 개수 (기본 500, 최소 1 이상 보장)
_EVAL_REPORT_SCAN_BATCH_SIZE = max(1, int(os.getenv("EVAL_REPORT_SCAN_BATCH_SIZE", "500")))

# [Step 2-3] 조사 제거 및 TF 계산을 위한 경량화된 한국어 불용어
_KOREAN_STOPWORDS = {
    "어떻게", "무엇인가요", "알려줘", "설명해줘", "어떤", "무엇", "이건", "저건", 
    "있나요", "어디서", "있을까", "인가요", "하는지", "방법", "대해", "대한", "그리고",
    "이", "그", "저", "것", "수", "등", "때", "위해", "관련", "관련된"
}

# [Step 2-3] 연속 처리를 위해 미리 정렬된 조사 튜플 (길이 역순)
_POSTPOSITIONS_SORTED = tuple(
    sorted(
        ['은', '는', '이', '가', '을', '를', '의', '에', '에게', '에서', '으로', '로', '와', '과', '도', '만'],
        key=len,
        reverse=True
    )
)

def _strip_postpositions(token: str) -> str:
    """조사(은/는/이/가/...)를 가능한 한 반복적으로 제거합니다."""
    stem = token
    while len(stem) > 1:
        stripped = False
        for josa in _POSTPOSITIONS_SORTED:
            if stem.endswith(josa) and len(stem) > len(josa):
                stem = stem[:-len(josa)]
                stripped = True
                break
        if not stripped:
            break
    return stem

def _extract_keywords(text: str) -> list[str]:
    """
    텍스트에서 핵심 키워드를 추출합니다 (KoNLPy/TF-IDF 대안 경량화 알고리즘).
    - 특수문자 제거
    - 공백 기준 분리
    - 기본적인 한국어 조사 제거 (은/는/이/가/을/를/의/에/에서/으로/로/와/과/도/만/에게)
    - 불용어(Stopwords) 필터링
    """
    cleaned = re.sub(r'[^\w\s]', '', text)
    tokens = cleaned.split()
    
    extracted: list[str] = []
    
    for token in tokens:
        if token in _KOREAN_STOPWORDS:
            continue
            
        stem = _strip_postpositions(token)
                
        # 추출된 단어가 2글자 이상이고 불용어가 아닌 경우만 보존
        if len(stem) > 1 and stem not in _KOREAN_STOPWORDS:
            extracted.append(stem)
            
    return extracted

async def _iter_eval_records(
    redis_conn: Any,
    key_pattern: str,
    max_scan_iterations: int,
    scan_batch_size: int = _EVAL_REPORT_SCAN_BATCH_SIZE
) -> AsyncIterator[dict[str, Any]]:
    """Redis SCAN 및 JSON 파싱을 수행하는 async 제너레이터 헬퍼"""
    cursor = 0
    iteration = 0
    
    while True:
        if iteration >= max_scan_iterations:
            break
        iteration += 1
        
        cursor, keys = await redis_conn.scan(cursor, match=key_pattern, count=scan_batch_size)
        
        for key in keys:
            key_str = key.decode("utf-8") if isinstance(key, bytes) else str(key)
            eval_hash = await redis_conn.hgetall(key_str)
            
            for _, raw_val in eval_hash.items():
                try:
                    val_str = raw_val.decode("utf-8") if isinstance(raw_val, bytes) else str(raw_val)
                    yield json.loads(val_str)
                except (JSONDecodeError, ValueError):
                    continue
                    
        if int(cursor) == 0:
            break

async def generate_eval_report() -> dict[str, Any]:
    """
    [Step 2-3] 분류된 '실패 응답'들의 현황 및 키워드 클러스터링 보고서를 생성합니다.
    FastAPI 엔드포인트를 통해 JSON 형태로 관리자 대시보드에 제공됩니다.
    
    기능:
    - 전체 분류(레이블) 분포 반환
    - 실패(hallucination, rag_retrieval_failure)로 분류된 질문(rag_query)들에서 핵심 키워드 추출
    - TF(Term Frequency) 기반 Top 5 키워드 클러스터링 도출
    """
    if not redis_client.is_connected():
        await redis_client.connect()
        
    labels_count: dict[str, int] = defaultdict(int)
    failed_queries: list[str] = []
    
    async for parsed in _iter_eval_records(
        redis_conn=redis_client.redis,
        key_pattern=f"{_EVAL_RESULT_PREFIX}*",
        max_scan_iterations=_EVAL_REPORT_MAX_SCAN_ITERATIONS
    ):
        label = parsed.get("label", "uncertain")
        labels_count[label] += 1
            
        # 실패 케이스의 질문 수집
        if label in ("hallucination", "rag_retrieval_failure"):
            query = parsed.get("rag_query")
            if query:
                failed_queries.append(query)
            
    # 키워드 TF 계산 (TF-IDF 경량 대안)
    keyword_counter: Counter = Counter()
    for q in failed_queries:
        keyword_counter.update(_extract_keywords(q))
        
    # 클러스터링 (상위 5개의 핵심 키워드로 대표되는 토픽 반환)
    top_5_keywords = [{"keyword": k, "count": c} for k, c in keyword_counter.most_common(5)]
    
    logger.info(
        "[OBS] Generated Admin Eval Report",
        extra={
            "total_evaluated": sum(labels_count.values()),
            "failed_query_count": len(failed_queries),
            "top_keyword": top_5_keywords[0]["keyword"] if top_5_keywords else None
        }
    )
    
    return {
        "status": "success",
        "total_evaluated": sum(labels_count.values()),
        "label_distribution": dict(labels_count),
        "top_failing_topics": top_5_keywords,
        "failed_query_count": len(failed_queries),
        "timestamp": _now_utc_iso()
    }
