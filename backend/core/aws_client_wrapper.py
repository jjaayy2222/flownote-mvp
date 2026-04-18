import os
import asyncio
import threading
import logging
import random
from typing import Optional, Callable, Any
from concurrent.futures import ThreadPoolExecutor

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError

from backend.core.config_validator import PersonalizedRAGConfig

logger = logging.getLogger(__name__)

class FatalSecurityError(SystemExit):
    """
    치명적인 보안 관련 에러에 사용되는 예외입니다. 
    일반 예외(Exception) 핸들러에서 삼켜지는 것(Swallowed)을 방지하고, 
    프로세스 Fail-fast(즉시 종료)를 보장하기 위해 SystemExit을 상속받습니다.
    """
    def __init__(self, log_message: str) -> None:
        # SystemExit.code 에 프로세스 종료 코드를 명시적으로 전달합니다.
        # 기존 파이썬 예외 표준(str(e))을 깨지 않기 위해 페이로드를 별도 해제합니다.
        super().__init__(1)
        self.log_message = log_message

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
