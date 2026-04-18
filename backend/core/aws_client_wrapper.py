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

# Boto3 기본 재시도 비활성화 (애플리케이션 레이어 권한 통제)
AWS_CONFIG = Config(
    retries={'max_attempts': 0, 'mode': 'standard'}
)

_session_lock = threading.Lock()
_boto_session: Optional[boto3.Session] = None


def get_boto3_session() -> boto3.Session:
    """
    동기(Synchronous) Boto3 Session 싱글톤 팩토리.
    이중 확인 락킹(Double-checked locking) 패턴으로 프로세스/포크 내 유일성을 보장 (Thread-Safe & Fork-Safe).
    """
    global _boto_session
    if _boto_session is None:
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

async def _invoke_with_full_jitter(func: Callable[[], Any]) -> Any:
    """
    명시적 Full Jitter 기반 앱 레벨 재시도 알고리즘 (Base Delay 1s, Cap 10s, Max 3 Retries).
    이중 증폭(Double retries) 방지를 위해 boto3 설정에서 max_attempts=0 지정 시에만 사용 권장.
    """
    max_retries = 3
    base_delay = 1.0
    cap_delay = 10.0
    
    for attempt in range(max_retries + 1):
        try:
            return await asyncio.to_thread(func)
            
        except (EndpointConnectionError, ReadTimeoutError) as e:
            is_transient = True
            error_code = type(e).__name__
            
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            
            if error_code in FATAL_CLIENT_ERRORS:
                logger.critical(
                    "[AWS][HARD-FAIL] Fatal ClientError: %s. Aborting immediately without retries.",
                    error_code
                )
                raise
            
            is_transient = error_code in TRANSIENT_CLIENT_ERRORS
            
            if not is_transient:
                logger.error("[AWS] Unhandled ClientError: %s", error_code)
                raise
                
        else:
            # loop exited via return; unreachable
            break
            
        if attempt == max_retries:
            logger.error("[AWS][RETRY] Max retries reached for transient error: %s", error_code)
            raise
            
        delay = min(cap_delay, base_delay * (2 ** attempt))
        jitter = random.uniform(0, delay)
        logger.warning(
            "[AWS][RETRY] Transient error %s. Retrying in %.2fs (Attempt %d/%d).",
            error_code, jitter, attempt + 1, max_retries
        )
        await asyncio.sleep(jitter)


async def fetch_global_pepper() -> str:
    """
    AWS Systems Manager Parameter Store(혹은 Secrets Manager)를 통해 
    global_pepper를 안전하게 메모리로만 페치합니다. (KMS 자동 복호화 포함)
    """
    session = await get_boto3_session_async()
    
    def _fetch() -> str:
        # Boto3 기본 재시도를 비활성화하고 독점 Full Jitter 사용
        client = session.client('ssm', config=AWS_CONFIG)
        response = client.get_parameter(
            Name='/v9/security/global_pepper',
            WithDecryption=True
        )
        return response['Parameter']['Value']
        
    try:
        pepper = await _invoke_with_full_jitter(_fetch)
        if not pepper:
            raise ValueError("SSM returned empty string for global_pepper")
        return pepper
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        logger.critical("[AWS][SECURITY] Failed to fetch global_pepper: %s", error_code)
        # 암호화 무단 오염 및 노출 방지를 위한 프로세스 중단 (Hard Fail-fast)
        raise SystemExit("Fatal Security Error: Cannot retrieve global_pepper. Process aborted to protect data integrity.")
    except Exception as e:
        logger.critical("[AWS][SECURITY] Unexpected error fetching pepper: %s", type(e).__name__)
        raise SystemExit("Fatal Security Error: Cannot retrieve global_pepper. Process aborted to protect data integrity.")
