import os
import asyncio
import threading
import logging
import random
from enum import Enum
from typing import Optional, Callable, Any, Union
from concurrent.futures import ThreadPoolExecutor

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError

from backend.core.config_validator import PersonalizedRAGConfig

logger = logging.getLogger(__name__)

class SecurityExitCode(Enum):
    """
    FatalSecurityError 발생 시의 표준화된 프로세스 종료 코드 체계입니다.
    무분별한 임의 숫자 사용을 방지하고, K8s 등 외부 모니터링 시스템과의 정합성을 유지합니다.
    """
    GENERIC_FAILURE = 1
    # 향후 AWS IAM(액세스 거부) 또는 네트워크(타임아웃) 등 
    # 세분화된 장애가 필요할 경우 여기에 추가 정의합니다.

class FatalSecurityError(SystemExit):
    """
    치명적인 보안 관련 에러에 사용되는 예외입니다. 
    일반 예외(Exception) 핸들러에서 삼켜지는 것(Swallowed)을 방지하고, 
    프로세스 Fail-fast(즉시 종료)를 보장하기 위해 SystemExit을 상속받습니다.
    """
    def __init__(self, log_message: str, exit_code: int | SecurityExitCode = SecurityExitCode.GENERIC_FAILURE) -> None:
        # 1. API 유연성 및 타입 안전성: Enum/int 수용 및 명시적 정규화
        if isinstance(exit_code, SecurityExitCode):
            raw_code = exit_code.value
        else:
            try:
                raw_code = int(exit_code)
            except (ValueError, TypeError):
                raw_code = 1  # 비정상 타입 유입 시 폴백(fallback)
        
        # SystemExit.code 에 프로세스 종료 코드를 명시적으로 전달합니다.
        super().__init__(raw_code)
        self.log_message = log_message
        self.exit_code_int = raw_code  # 원시 정수 속성을 노출시켜 하위 계층 편의 제공
        
        # 2. 관측성 보장: 다운스트림 로거가 Enum의 풍부한 시맨틱(.name 등)을 읽을 수 있도록 보존
        try:
            self.exit_code_enum = SecurityExitCode(raw_code)
        except ValueError:
            self.exit_code_enum = None

    def __str__(self) -> str:
        return self.log_message

# Boto3 기본 재시도 비활성화 (애플리케이션 레이어 권한 통제)
AWS_CONFIG = Config(
    retries={'max_attempts': 0, 'mode': 'standard'}
)

_session_lock = threading.Lock()
_boto_session: Optional[boto3.Session] = None


def get_boto3_session() -> boto3.Session:
    """
    동기(Synchronous) Boto3 Session 싱글톤 팩토리.
    단일 공용 Lock을 사용하여 초기화 스레드 안전성을 보장합니다.
    """
    global _boto_session
    with _session_lock:
        if _boto_session is None:
            logger.info("[AWS] Initializing shared Boto3 Session (Lazy Initialization)")
            _boto_session = boto3.Session()
        return _boto_session


async def get_boto3_session_async() -> boto3.Session:
    """
    비동기 파이썬 환경에서 데드락(Deadlock)을 방지하기 위해 
    Boto3 초기화 연산을 기본 이벤트 루프 스레드 풀에 오프로드(Offload)합니다.
    """
    global _boto_session
    if _boto_session is not None:
        return _boto_session
    return await asyncio.to_thread(get_boto3_session)


TRANSIENT_CLIENT_ERRORS = {"ThrottlingException"}
FATAL_CLIENT_ERRORS = {
    "LimitExceededException",
    "AccessDeniedException",
    "NotFoundException",
    "ParameterNotFound",
}


async def fetch_global_pepper() -> str:
    """
    AWS Systems Manager Parameter Store(혹은 Secrets Manager)를 통해 
    global_pepper를 안전하게 메모리로만 페치합니다. (KMS 자동 복호화 포함)
    """
    session = await get_boto3_session_async()
    client = session.client('ssm', config=AWS_CONFIG)

    max_retries = 3
    base_delay = 1.0
    cap_delay = 10.0

    for retry_index in range(max_retries + 1):
        try:
            response = await asyncio.to_thread(
                client.get_parameter,
                Name="/v9/security/global_pepper",
                WithDecryption=True,
            )
            pepper = response["Parameter"]["Value"]
            if not pepper:
                raise ValueError("SSM returned empty string for global_pepper")
            return pepper

        except (EndpointConnectionError, ReadTimeoutError) as e:
            error_code = type(e).__name__
            is_transient = True

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")

            if error_code in FATAL_CLIENT_ERRORS:
                logger.critical(
                    "[AWS][HARD-FAIL] Fatal ClientError: %s. Aborting immediately without retries.",
                    error_code,
                )
                raise FatalSecurityError(f"Fatal Security Error: {error_code}") from e

            is_transient = error_code in TRANSIENT_CLIENT_ERRORS
            if not is_transient:
                logger.error("[AWS] Unhandled ClientError: %s", error_code)
                raise FatalSecurityError(f"Unhandled AWS exception: {error_code}") from e
                
        except Exception as e:
            logger.critical("[AWS][SECURITY] Unexpected error fetching pepper: %s", type(e).__name__)
            raise FatalSecurityError("Fatal Security Error: Unexpected exception during pepper retrieval.") from e

        if retry_index == max_retries:
            logger.error("[AWS][RETRY] Max retries reached for transient error: %s", error_code)
            raise FatalSecurityError(f"Max retries reached: {error_code}") from e

        delay = min(cap_delay, base_delay * (2**retry_index))
        jitter = random.uniform(0, delay)
        
        current_retry = retry_index + 1
        logger.warning(
            "[AWS][RETRY] Transient error %s. Retrying in %.2fs (Retry %d/%d).",
            error_code,
            jitter,
            current_retry,
            max_retries,
        )
        await asyncio.sleep(jitter)
