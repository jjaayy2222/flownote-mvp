# backend/services/finetune_service.py

"""
[v9.0] Phase 1 - Step 1: Fine-tuning 서비스 엔진

Golden Dataset(JSONL)을 OpenAI Fine-tuning API에 업로드하고
Fine-tuning Job을 생성·상태 폴링·Redis 상태 동기화까지 담당합니다.

관련 이슈: #1045
브랜치: feature/issue-1045-adaptive-finetune
"""

import asyncio
import logging
import os
import time
from enum import Enum
from pathlib import Path
from typing import Optional

from openai import OpenAI, APIError, APIConnectionError

from backend.config import ModelConfig  # type: ignore[import]
from backend.services.redis_pubsub import redis_client  # type: ignore[import]
from backend.utils import mask_pii_id  # type: ignore[import]

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# 설정 상수 (모두 환경 변수 기반 — 하드코딩 금지)
# ─────────────────────────────────────────────────────────────

# Redis 키 네임스페이스: v9:finetune:{job_id} 패턴 준수 (기획 문서: v9.1_adaptive_finetune_tasks.md)
_FINETUNE_REDIS_KEY_PREFIX: str = os.getenv(
    "FINETUNE_REDIS_KEY_PREFIX", "v9:finetune:job:"
)

# 현재 운영 중인 파인튜닝된 모델 ID를 추적하는 Redis 키 (Hot-swap 지원)
# 패턴: {service}:{version}:{key} 네임스페이스 준수
_FINETUNE_ACTIVE_MODEL_KEY: str = os.getenv(
    "FINETUNE_ACTIVE_MODEL_KEY", "v9:finetune:current_model_id"
)

# 파인튜닝용 JSONL 파일 기본 저장 경로
# 환경 변수로 재정의하여 멀티 리전/환경 대응 가능 (기획: STORAGE_BASE_PATH 전략)
_FINETUNE_DATA_DIR: Path = Path(
    os.getenv(
        "FINETUNE_DATA_DIR",
        str(Path(__file__).resolve().parent.parent.parent / "data" / "golden_dataset"),
    )
)

# Job 상태 폴링 간격(초) — 환경 변수로 오버라이드 가능
_FINETUNE_POLL_INTERVAL_SECS: int = int(
    os.getenv("FINETUNE_POLL_INTERVAL_SECS", "30")
)

# Job 완료 대기 최대 시간(초) — 기본 2시간 (환경 변수로 오버라이드 가능)
_FINETUNE_POLL_TIMEOUT_SECS: int = int(
    os.getenv("FINETUNE_POLL_TIMEOUT_SECS", str(2 * 60 * 60))
)

# Redis에 Job 상태를 보관하는 TTL (기본 7일)
_FINETUNE_REDIS_TTL_SECS: int = int(
    os.getenv("FINETUNE_REDIS_TTL_SECS", str(7 * 24 * 60 * 60))
)

# 파인튜닝 Job 생성 시 사용할 기반 모델 (환경 변수로 오버라이드 가능)
_FINETUNE_BASE_MODEL: str = os.getenv("FINETUNE_BASE_MODEL", "gpt-4o-mini-2024-07-18")


# ─────────────────────────────────────────────────────────────
# 도메인 타입: Job 상태 Enum
# ─────────────────────────────────────────────────────────────


class FinetuneJobStatus(str, Enum):
    """
    OpenAI Fine-tuning Job의 생명 주기 상태.
    str을 상속해 Redis 직렬화(value 직접 사용) 및 로그 가독성을 높입니다.
    """

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def from_openai_status(cls, status: str) -> "FinetuneJobStatus":
        """
        OpenAI API 응답의 status 문자열을 FinetuneJobStatus로 변환합니다.
        알 수 없는 상태는 RUNNING으로 처리하고 경고를 발생시킵니다.
        """
        mapping = {
            "validating_files": cls.PENDING,
            "queued": cls.PENDING,
            "running": cls.RUNNING,
            "succeeded": cls.SUCCEEDED,
            "failed": cls.FAILED,
            "cancelled": cls.CANCELLED,
        }
        mapped = mapping.get(status)
        if mapped is None:
            logger.warning(
                "[OBS] Unknown OpenAI fine-tuning job status encountered.",
                extra={"raw_status": status},
            )
            return cls.RUNNING
        return mapped


# ─────────────────────────────────────────────────────────────
# 내부 헬퍼: 공통 유틸리티
# ─────────────────────────────────────────────────────────────


def _preview_id(value: str, length: int = 20) -> str:
    """
    민감하지 않은 식별자(모델 ID 등)를 로그에서 가독성 있게 축약합니다.
    동일한 슬라이싱 로직이 여러 곳에 중복되는 것을 방지합니다(DRY 원칙).

    Args:
        value: 원본 문자열
        length: 축약 기준 길이 (기본: 20자)

    Returns:
        length보다 짧으면 원본, 길면 앞 length자 + '...'
    """
    return value[:length] + "..." if len(value) > length else value


def _elapsed_secs(start: float) -> float:
    """
    폴링 시작 시점(start)으로부터 현재까지 경과한 시간을 초 단위로 반환합니다.
    time.monotonic()을 사용하기 때문에 NTP 조정이나 시스템 시간 변경에 영향받지 않는
    단조 증가(monotonic) 경과 시간을 측정합니다. 실제 현재 시각과는 일치하지 않을 수 있습니다.
    결과는 항상 0 이상으로 클램핑되어 음수 값 발생을 방지합니다.
    시간 측정 로직을 단일 지점으로 중앙화하여 일관성을 보장합니다(DRY 원칙).

    Args:
        start: 기준 시작 시간 (time.monotonic() 반환값)

    Returns:
        단조 경과 시간 (초, float), 항상 >= 0.0
    """
    return max(0.0, time.monotonic() - start)


# Redis Hash에서 타측에서 교체할 수 없는 핵심 피드 키 목록
# extra_fields에 이 키가 포함되어도 저장에서 제외(필터링)됩니다.
_RESERVED_REDIS_KEYS: frozenset[str] = frozenset({"status", "fine_tuned_model"})


# ─────────────────────────────────────────────────────────────
# 내부 헬퍼: OpenAI 클라이언트 생성
# ─────────────────────────────────────────────────────────────


def _get_openai_client() -> OpenAI:
    """
    기존 ModelConfig 패턴을 준용하여 GPT-4o-mini 기반 OpenAI 클라이언트를 반환합니다.
    Fine-tuning API는 base_url 없이 공식 OpenAI 엔드포인트를 사용해야 합니다.

    환경 변수 `GPT4O_MINI_API_KEY`를 통해 API 키를 주입받습니다.

    Raises:
        ValueError: GPT4O_MINI_API_KEY가 설정되지 않은 경우.
    """
    api_key = ModelConfig.GPT4O_MINI_API_KEY
    if not api_key:
        raise ValueError(
            "[OBS] GPT4O_MINI_API_KEY is not set. "
            "Fine-tuning API requires a valid OpenAI API key."
        )
    # Fine-tuning API는 공식 OpenAI 엔드포인트 전용이므로 base_url을 별도 설정하지 않습니다.
    return OpenAI(api_key=api_key)


# ─────────────────────────────────────────────────────────────
# 내부 헬퍼: Redis 상태 관리
# ─────────────────────────────────────────────────────────────


async def _save_job_status_to_redis(
    job_id: str,
    status: FinetuneJobStatus,
    fine_tuned_model: Optional[str] = None,
    extra_fields: Optional[dict[str, str]] = None,
) -> None:
    """
    Fine-tuning Job 상태를 Redis Hash에 저장합니다.
    키 패턴: {_FINETUNE_REDIS_KEY_PREFIX}{job_id}

    Args:
        job_id: OpenAI Fine-tuning Job ID (민감 식별자 — 로그에 원본을 남기지 않습니다.)
        status: 현재 Job 상태 (FinetuneJobStatus)
        fine_tuned_model: 성공 시 반환되는 파인튜닝된 모델 ID (Optional)
        extra_fields: 상태 외 추가로 저장할 메타데이터 (timed_out, last_error 등)
    """
    if not redis_client.is_connected():
        await redis_client.connect()

    redis_key = f"{_FINETUNE_REDIS_KEY_PREFIX}{job_id}"
    mapping: dict[str, str] = {"status": status.value}
    if fine_tuned_model:
        mapping["fine_tuned_model"] = fine_tuned_model
    if extra_fields:
        # 핵심 키(status, fine_tuned_model)가 오버라이드되지 않도록 예약 키를 필터링합니다.
        safe_extra = {k: v for k, v in extra_fields.items() if k not in _RESERVED_REDIS_KEYS}
        # 집합 교집(∩)으로 충돌한 예약 키를 직접 하이라이팅하여 의도를 명확히 표현합니다.
        skipped = set(extra_fields) & _RESERVED_REDIS_KEYS
        if skipped:
            # [INTENTIONAL WARNING] 이 경고는 호출자가 예약 키를 extra_fields에 잘못 전달한
            # 프로그래밍 버그 감지용입니다. 정상 운영 중에는 절대 발생해서는 안 됩니다.
            # 빈번한 노이즈가 우려되어 레벨을 낮추는 것은 부적합합니다 — WARNING을 유지합니다.
            logger.warning(
                "[OBS] extra_fields contained reserved Redis keys and were ignored.",
                extra={
                    # ELK/Datadog 등 알림 규칙 대응용 기계 판독 머커
                    "event": "reserved_redis_keys_in_extra_fields",
                    "intentional_warning": True,
                    "skipped_reserved_redis_keys": sorted(skipped),
                    # 운영자가 어떤 Job에서 발생한 경고인지 추적할 수 있도록 마스킹 ID 포함
                    "job_id_hash": mask_pii_id(job_id),
                    "redis_key_prefix": _FINETUNE_REDIS_KEY_PREFIX,
                },
            )
        if safe_extra:
            mapping.update(safe_extra)

    await redis_client.redis.hset(redis_key, mapping=mapping)
    await redis_client.redis.expire(redis_key, _FINETUNE_REDIS_TTL_SECS)

    logger.info(
        "[OBS] Fine-tuning job status saved to Redis.",
        extra={
            "job_id_hash": mask_pii_id(job_id),
            "status": status.value,
            "ttl_secs": _FINETUNE_REDIS_TTL_SECS,
        },
    )


async def _set_active_model_in_redis(fine_tuned_model_id: str) -> None:
    """
    성공적으로 완료된 파인튜닝 모델 ID를 Redis의 Active Model 키에 저장합니다.
    이 값은 Hot-swap 메커니즘에서 LangGraph 에이전트가 참조합니다.

    키: {_FINETUNE_ACTIVE_MODEL_KEY} (예: "v9:finetune:current_model_id")
    """
    if not redis_client.is_connected():
        await redis_client.connect()

    await redis_client.redis.set(_FINETUNE_ACTIVE_MODEL_KEY, fine_tuned_model_id)
    logger.info(
        "[OBS] Active fine-tuned model ID updated in Redis.",
        extra={
            "active_model_key": _FINETUNE_ACTIVE_MODEL_KEY,
            # 모델 ID 자체는 민감 정보가 아니므로 일부만 마스킹하여 추적성 유지
            "model_id_preview": _preview_id(fine_tuned_model_id),
        },
    )


# ─────────────────────────────────────────────────────────────
# 핵심 서비스 함수 (동기 헬퍼 + 비동기 퍼블릭 API)
# ─────────────────────────────────────────────────────────────


def _upload_jsonl_and_create_finetune_job_sync(
    jsonl_filename: str,
    base_model: str,
) -> Optional[str]:
    """
    [동기 전용 내부 헬퍼] JSONL 업로드 및 Fine-tuning Job 생성의 블로킹 I/O를 담당합니다.
    이벤트 루프 차단 방지를 위해 퍼블릭 API인 upload_jsonl_and_create_finetune_job()에서
    asyncio.to_thread()를 통해 워커 스레드로 위임합니다.

    Args:
        jsonl_filename: JSONL 파일명 (경로 없이 파일명만)
        base_model: 파인튜닝에 사용할 기반 모델 ID

    Returns:
        OpenAI Fine-tuning Job ID (성공 시), 또는 None (실패 시)
    """
    jsonl_path = _FINETUNE_DATA_DIR / jsonl_filename

    try:
        client = _get_openai_client()

        # 1. JSONL 파일 업로드 (blocking file I/O — 스레드 풀에서 안전)
        with open(jsonl_path, "rb") as f:
            upload_response = client.files.create(file=f, purpose="fine-tune")

        file_id = upload_response.id
        logger.info(
            "[OBS] JSONL file uploaded to OpenAI Files API.",
            extra={
                "file_id_preview": _preview_id(file_id, length=12),
                "jsonl_filename": jsonl_filename,
            },
        )

        # 2. Fine-tuning Job 생성 (blocking network I/O — 스레드 풀에서 안전)
        job_response = client.fine_tuning.jobs.create(
            training_file=file_id,
            model=base_model,
        )

        logger.info(
            "[OBS] Fine-tuning job object created via OpenAI API.",
            extra={
                "job_id_hash": mask_pii_id(job_response.id),
                "initial_status": job_response.status,
                "base_model": base_model,
            },
        )

        return job_response.id

    except APIConnectionError as e:
        logger.error(
            "[OBS] OpenAI API connection error during fine-tuning job creation.",
            extra={"error": str(e)},
            exc_info=True,
        )
        return None
    except APIError as e:
        logger.error(
            "[OBS] OpenAI API error during fine-tuning job creation.",
            extra={"error_code": getattr(e, "code", "unknown"), "error": str(e)},
            exc_info=True,
        )
        return None


async def upload_jsonl_and_create_finetune_job(
    jsonl_filename: str,
    base_model: Optional[str] = None,
) -> Optional[str]:
    """
    Golden Dataset JSONL 파일을 OpenAI Files API에 업로드하고
    Fine-tuning Job을 생성합니다.

    블로킹 I/O(파일 읽기, 동기 OpenAI 클라이언트)를 asyncio.to_thread()로 워커 스레드에 위임하여
    이벤트 루프 차단을 방지합니다.

    Args:
        jsonl_filename: data/golden_dataset/ 하위의 JSONL 파일명 (예: "2026-04-12.jsonl")
        base_model: 파인튜닝에 사용할 기반 모델 (기본: _FINETUNE_BASE_MODEL 환경 변수)

    Returns:
        생성된 Fine-tuning Job ID (성공 시), 또는 None (실패 시)

    Raises:
        FileNotFoundError: 지정된 JSONL 파일이 존재하지 않는 경우
        ValueError: API 키가 설정되지 않은 경우
    """
    jsonl_path = _FINETUNE_DATA_DIR / jsonl_filename

    if not jsonl_path.exists():
        raise FileNotFoundError(
            f"[OBS] JSONL file not found for fine-tuning upload: {jsonl_path}"
        )

    target_model = base_model or _FINETUNE_BASE_MODEL

    logger.info(
        "[OBS] Starting JSONL upload and fine-tuning job creation.",
        extra={
            "jsonl_filename": jsonl_filename,
            "base_model": target_model,
        },
    )

    # 블로킹 I/O 전체를 워커 스레드로 위임 — 이벤트 루프 차단 방지
    job_id = await asyncio.to_thread(
        _upload_jsonl_and_create_finetune_job_sync,
        jsonl_filename,
        target_model,
    )

    if job_id is not None:
        initial_status = FinetuneJobStatus.PENDING
        await _save_job_status_to_redis(job_id=job_id, status=initial_status)
        logger.info(
            "[OBS] Fine-tuning job creation complete. Initial status saved to Redis.",
            extra={
                "job_id_hash": mask_pii_id(job_id),
                "initial_status": initial_status.value,
            },
        )

    return job_id


async def poll_finetune_job_until_done(job_id: str) -> FinetuneJobStatus:
    """
    Fine-tuning Job 상태를 주기적으로 폴링하여 완료(succeeded/failed/cancelled)까지 대기합니다.
    상태 변경이 발생할 때마다 Redis에 동기화합니다.

    Args:
        job_id: OpenAI Fine-tuning Job ID

    Returns:
        FinetuneJobStatus: 최종 종료 상태 (SUCCEEDED | FAILED | CANCELLED)

    Note:
        - _FINETUNE_POLL_TIMEOUT_SECS 초과 시 FAILED 상태를 Redis에 기록하고 폴링을 종료합니다.
        - Discord 알림은 [OBS] 태그가 붙은 로그를 DiscordAlertHandler가 자동 감지하여 전송합니다.
          (별도의 Discord API 호출은 없습니다 — backend/utils/observability.py 참조)
        - 네트워크 오류 발생 시에도 폴링을 유지하며 에러 로그만 남깁니다.
    """
    terminal_statuses = {
        FinetuneJobStatus.SUCCEEDED,
        FinetuneJobStatus.FAILED,
        FinetuneJobStatus.CANCELLED,
    }

    try:
        client = _get_openai_client()
    except ValueError as e:
        logger.error("[OBS] Cannot poll fine-tuning job: API client creation failed.", extra={"error": str(e)})
        return FinetuneJobStatus.FAILED

    # 실제 벽시계 시간 기반으로 타임아웃 측정 (jobs.retrieve 지연 시간 포함)
    start_time: float = time.monotonic()
    deadline: float = start_time + _FINETUNE_POLL_TIMEOUT_SECS

    logger.info(
        "[OBS] Starting fine-tuning job polling.",
        extra={
            "job_id_hash": mask_pii_id(job_id),
            "poll_interval_secs": _FINETUNE_POLL_INTERVAL_SECS,
            "timeout_secs": _FINETUNE_POLL_TIMEOUT_SECS,
        },
    )

    # do-while 패턴: 첫 번째 조회는 즉시 실행하여 빠른 실패/성공을 즉각 반영합니다.
    # 이후 순환부터 sleep을 선행하여 불필요한 API 호출 빈도를 조절합니다.
    first_attempt = True

    while True:
        # 이터레이션 시작 시 한 번만 샘플링하여 루프 내 time.monotonic() 호출 불일치 방지
        now: float = time.monotonic()
        if now >= deadline:
            break
        if not first_attempt:
            await asyncio.sleep(_FINETUNE_POLL_INTERVAL_SECS)
            # deadline을 차감하는 대신 time.monotonic()을 사용해 항상 정확히 확인
            now = time.monotonic()
            if now >= deadline:
                break
        first_attempt = False

        try:
            job_data = await asyncio.to_thread(client.fine_tuning.jobs.retrieve, job_id)
            current_status = FinetuneJobStatus.from_openai_status(job_data.status)
            fine_tuned_model: Optional[str] = job_data.fine_tuned_model

            # Redis 상태 동기화
            await _save_job_status_to_redis(
                job_id=job_id,
                status=current_status,
                fine_tuned_model=fine_tuned_model,
            )

            if current_status in terminal_statuses:
                if current_status == FinetuneJobStatus.SUCCEEDED and fine_tuned_model:
                    # Hot-swap: 완료된 모델 ID를 Active Model로 등록
                    await _set_active_model_in_redis(fine_tuned_model)
                    logger.info(
                        "[OBS] Fine-tuning succeeded. New model is now active.",
                        extra={
                            "job_id_hash": mask_pii_id(job_id),
                            "model_id_preview": _preview_id(fine_tuned_model),
                        },
                    )
                else:
                    logger.warning(
                        "[OBS] Fine-tuning job ended with non-success status.",
                        extra={
                            "job_id_hash": mask_pii_id(job_id),
                            "final_status": current_status.value,
                        },
                    )
                return current_status

        except APIConnectionError as e:
            # 일시적 네트워크 오류 — 재시도 허용
            logger.warning(
                "[OBS] Transient connection error during fine-tuning job polling. Will retry.",
                extra={"job_id_hash": mask_pii_id(job_id), "error": str(e), "elapsed_secs": round(_elapsed_secs(start_time), 1)},
            )
        except APIError as e:
            status_code: int = getattr(e, "status_code", 0) or 0
            if status_code < 500:
                # 4xx: 잘못된 Job ID, 권한 오류 등 영구적 실패 — 즉시 중단
                logger.error(
                    "[OBS] Permanent API error during fine-tuning job polling. Aborting poll.",
                    extra={
                        "job_id_hash": mask_pii_id(job_id),
                        "status_code": status_code,
                        "error": str(e),
                    },
                    exc_info=True,
                )
                await _save_job_status_to_redis(job_id=job_id, status=FinetuneJobStatus.FAILED)
                return FinetuneJobStatus.FAILED
            else:
                # 5xx: 서버 오류 — 재시도 허용
                logger.error(
                    "[OBS] Transient server error during fine-tuning job polling. Will retry.",
                    extra={"job_id_hash": mask_pii_id(job_id), "status_code": status_code, "error": str(e)},
                )

    # 타임아웃 만료: start_time 기준으로 실제 경과 시간을 계산하고 음수가 되지 않도록 클램핑
    actual_elapsed = _elapsed_secs(start_time)
    logger.error(
        "[OBS] Fine-tuning job polling timed out.",
        extra={
            "job_id_hash": mask_pii_id(job_id),
            "timeout_secs": _FINETUNE_POLL_TIMEOUT_SECS,
            "actual_elapsed_secs": round(actual_elapsed, 1),
        },
    )
    # 타임아웃 메타데이터를 Redis에 준영속 기록하여 다운스트림이 상태를 식별할 수 있도록 합니다.
    await _save_job_status_to_redis(
        job_id=job_id,
        status=FinetuneJobStatus.FAILED,
        extra_fields={
            "timed_out": "true",
            "actual_elapsed_secs": str(round(actual_elapsed, 1)),
        },
    )
    return FinetuneJobStatus.FAILED


async def get_active_finetune_model() -> Optional[str]:
    """
    Redis에서 현재 활성화된 파인튜닝 모델 ID를 조회합니다.
    LangGraph 에이전트의 Hot-swap 메커니즘에서 호출합니다.

    Returns:
        활성 파인튜닝 모델 ID (문자열), 또는 등록된 모델이 없으면 None
    """
    if not redis_client.is_connected():
        await redis_client.connect()

    raw = await redis_client.redis.get(_FINETUNE_ACTIVE_MODEL_KEY)
    if raw is None:
        return None

    model_id: str = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    return model_id if model_id else None
