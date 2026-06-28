import asyncio
import logging
import random
import threading
from enum import Enum
from typing import Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError

logger = logging.getLogger(__name__)


class SecurityExitCode(Enum):
    """
    FatalSecurityError 발생 시의 표준화된 프로세스 종료 코드 체계입니다.
    Standardized process exit code system for FatalSecurityError.

    무분별한 임의 숫자 사용을 방지하고, K8s 등 외부 모니터링 시스템과의 정합성을 유지합니다.
    Prevents the use of arbitrary magic numbers and maintains consistency with external monitoring systems (e.g., K8s).
    """

    GENERIC_FAILURE = 1
    # 향후 AWS IAM(액세스 거부) 또는 네트워크(타임아웃) 등
    # 세분화된 장애가 필요할 경우 여기에 추가 정의합니다.


MIN_OS_EXIT_CODE = 1
MAX_OS_EXIT_CODE = 255


class FatalSecurityError(SystemExit):
    """
    치명적인 보안 관련 에러에 사용되는 예외 클래스입니다.
    Exception used for fatal security-related errors.

    일반 예외(Exception) 핸들러에서 에러가 삼켜지는 현상(Swallowed)을 방지하고, 프로세스의 Fail-fast(즉시 종료)를 보장하기 위해 SystemExit을 상속받습니다.
    Inherits from SystemExit to prevent errors from being swallowed by generic exception handlers and ensures fail-fast process termination.

    Notes:
        [종료 코드 정규화 정책 / Exit Code Normalization Policy]
        임의의 `exit_code` 입력은 안전한 OS 종료 코드 범위(`MIN_OS_EXIT_CODE` ~ `MAX_OS_EXIT_CODE`)로 자동 정규화됩니다.
        정상 종료로 오인될 수 있는 `0`이나 허용 범위를 넘어서는 값, 혹은 Int 캐스팅이 불가능한 타입이 주입될 경우, 안전성을 위해 `SecurityExitCode.GENERIC_FAILURE`로 자동 폴백(Fallback) 처리됩니다.

    Args:
        log_message (str): 로깅 및 출력에 사용할 에러 메시지.
        exit_code (int | SecurityExitCode): 시스템 종료 시 반환할 종료 코드. 기본값은 `SecurityExitCode.GENERIC_FAILURE` (1).
    """

    def __init__(
        self,
        log_message: str,
        exit_code: int | SecurityExitCode = SecurityExitCode.GENERIC_FAILURE,
    ) -> None:
        # 공통 로깅 메타데이터(SIEM/APM용 구조화 필드) 사전 선언
        injected_type = type(exit_code).__name__
        base_extra = {
            "security_violation": True,
            "invalid_parameter": "exit_code",
            "injected_type": injected_type,
        }

        # 1. API 유연성 및 타입 안전성: Enum/int 수용 및 명시적 정규화
        if isinstance(exit_code, SecurityExitCode):
            raw_code = exit_code.value
        elif isinstance(exit_code, bool):
            # 파이썬에서 bool(True/False)은 int의 서브클래스이므로 int()에 의해 조용히 1/0으로 파싱됩니다.
            # 이와 같은 명시적인 오용(Misuse)은 Fallback으로 덮지 않고 즉각적인 TypeError로 개발자에게 피드백합니다.

            # [알럿 격상 정책]:
            # 이건 단순한 폴백 복구가 아닌, 보안 코드에 인증 불가 타입이 삽입된 명백한 논리 오류(개발 시점 이슈)입니다.
            # APM에 치명적 위반으로 리포팅하도록 ERROR 레벨을 고수하여 Ops 모니터링 가시성을 보장합니다.
            logger.error(
                "[AWS][SECURITY] Boolean is implicitly castable to int, but rejected as exit_code (type=%s). Raising TypeError.",
                injected_type,
                extra={**base_extra, "reason": "invalid_type"},
            )
            # 런타임 값의 PII 유출을 방지하기 위해 값 대신 Type을 노출하여 디버깅을 지원합니다.
            raise TypeError(
                f"Configuration Error: 'exit_code' parameter rejected. "
                f"Expected int or SecurityExitCode, but explicitly got type: {injected_type}."
            )
        else:
            # 방어적 정규화: float, Decimal 등 비표준 수치 타입도 int로 명시적으로 캐스팅합니다.
            # Defensive normalization: explicitly cast to int for non-standard numeric types (e.g., float, Decimal).
            # SecurityExitCode, bool 분기는 위에서 처리되었으며, 변환 불가 타입은 GENERIC_FAILURE로 폴백됩니다.
            try:
                raw_code = int(exit_code)
            except (ValueError, TypeError):
                raw_code = SecurityExitCode.GENERIC_FAILURE.value
                logger.warning(
                    "[AWS][SECURITY] Non-castable exit_code type provided: %s. Falling back to GENERIC_FAILURE.",
                    injected_type,
                    extra={**base_extra, "reason": "invalid_type"},
                )

        # OS Exit Code 바운더리 검증
        # 0은 정상 종료인 false-positive를 유발하므로 허용하지 않으며, MAX 초과는 Unix에서 모듈로 연산됨
        if not (MIN_OS_EXIT_CODE <= raw_code <= MAX_OS_EXIT_CODE):
            logger.warning(
                "[AWS][SECURITY] exit_code %s is out of valid OS bounds (%d-%d). Falling back to GENERIC_FAILURE.",
                raw_code,
                MIN_OS_EXIT_CODE,
                MAX_OS_EXIT_CODE,
                extra={
                    **base_extra,
                    "reason": "out_of_bounds",
                    "out_of_bounds_value": raw_code,
                },
            )
            raw_code = SecurityExitCode.GENERIC_FAILURE.value

        # SystemExit.code 에 프로세스 종료 코드를 명시적으로 전달합니다.
        super().__init__(raw_code)
        self.log_message = log_message
        self.exit_code_int = raw_code  # 원시 정수 속성을 노출시켜 하위 계층 편의 제공

        # 2. 관측성 보장: 다운스트림 로거가 Enum의 풍부한 시맨틱(.name 등)을 읽을 수 있도록 보존
        self.exit_code_enum: Optional[SecurityExitCode]
        try:
            self.exit_code_enum = SecurityExitCode(raw_code)
        except ValueError:
            self.exit_code_enum = None

    def __str__(self) -> str:
        return self.log_message


# Boto3 기본 재시도 비활성화 (애플리케이션 레이어 권한 통제)
AWS_CONFIG = Config(retries={"max_attempts": 0, "mode": "standard"})

_session_lock = threading.Lock()
_boto_session: Optional[boto3.Session] = None


def get_boto3_session() -> boto3.Session:
    """
    동기(Synchronous) 방식의 Boto3 Session 싱글톤 팩토리 함수입니다.
    Synchronous Boto3 Session singleton factory.

    단일 공용 Lock(`_session_lock`)을 사용하여 초기화 시 스레드 안전성(Thread-Safety)을 보장합니다. 지연 초기화(Lazy Initialization) 패턴을 적용합니다.

    Returns:
        boto3.Session: 초기화된 공용 Boto3 세션 객체.
    """
    global _boto_session
    with _session_lock:
        if _boto_session is None:
            logger.info("[AWS] Initializing shared Boto3 Session (Lazy Initialization)")
            _boto_session = boto3.Session()
        return _boto_session


async def get_boto3_session_async() -> boto3.Session:
    """
    비동기(Asynchronous) 환경용 Boto3 Session 팩토리 함수입니다.
    Asynchronous Boto3 Session factory.

    비동기 파이썬 환경(Asyncio)에서 블로킹 연산으로 인한 데드락(Deadlock)을 방지하기 위해, Boto3 초기화 연산을 기본 이벤트 루프의 스레드 풀로 오프로드(Offload)합니다.

    Returns:
        boto3.Session: 초기화된 공용 Boto3 세션 객체.
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
    AWS Systems Manager Parameter Store에서 전역 페퍼(Global Pepper) 값을 안전하게 페치합니다.
    Fetches the global pepper securely from AWS Systems Manager Parameter Store.

    값은 디스크에 저장되지 않고 메모리에만 적재되며, KMS를 통해 자동 복호화(`WithDecryption=True`)됩니다.
    지수 백오프(Exponential Backoff) 및 지터(Jitter)가 적용된 재시도(Retry) 로직이 내장되어 있습니다.

    Returns:
        str: AWS SSM에서 조회한 복호화된 페퍼 문자열.

    Raises:
        FatalSecurityError: SSM에서 값을 가져오는 데 실패하거나(재시도 초과), 복구할 수 없는 AWS 권한/네트워크 예외가 발생한 경우.
        ValueError: SSM에서 조회한 페퍼 값이 빈 문자열일 경우.
    """
    session = await get_boto3_session_async()
    client = session.client("ssm", config=AWS_CONFIG)

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
            # Validate and return pepper; reject empty strings immediately
            if not (pepper := response["Parameter"]["Value"]):
                raise ValueError("SSM returned empty string for global_pepper")
            return pepper

        except (EndpointConnectionError, ReadTimeoutError) as e:
            error_code = type(e).__name__
            last_error: BaseException = (
                e  # except 블록 종료 후 예외 체인 보존을 위해 별도 변수에 캡처
            )
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
                raise FatalSecurityError(
                    f"Unhandled AWS exception: {error_code}"
                ) from e
            last_error = e  # except 블록 종료 후 예외 체인 보존을 위해 별도 변수에 캡처

        except Exception as e:
            logger.critical(
                "[AWS][SECURITY] Unexpected error fetching pepper: %s", type(e).__name__
            )
            raise FatalSecurityError(
                "Fatal Security Error: Unexpected exception during pepper retrieval."
            ) from e

        if retry_index == max_retries:
            logger.error(
                "[AWS][RETRY] Max retries reached for transient error: %s", error_code
            )
            raise FatalSecurityError(
                f"Max retries reached: {error_code}"
            ) from last_error

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

    # NOTE: 이 라인은 정상적인 제어 흐름에서 절대 도달하지 않습니다.
    # 모든 루프 반복은 return(성공) 또는 raise(실패)로 종료되므로, 루프 탈출 자체가 불가능합니다.
    # 이 구문은 오직 정적 분석 도구(Pyrefly, mypy 등)의 'Missing return' 경고를 억제하기 위한 타입 안전망입니다.
    # NOTE: This line is unreachable in normal control flow.
    # Every loop iteration terminates with either return (success) or raise (failure).
    # This exists solely to satisfy the static type checker's return annotation requirement.
    raise FatalSecurityError("Unexpected exit from retry loop without return or raise")
