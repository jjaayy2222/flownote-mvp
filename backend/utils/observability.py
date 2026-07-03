# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/utils/observability.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - 관측성(Observability) 및 알림 유틸리티 모듈.

시스템 로그, 예외 이벤트, 임계치 위반 등을 감지하여
중앙 집중형 이벤트 로깅 및 외부 알림(Discord 등)을 담당합니다.

FlowNote MVP - Observability and Alerting Utilities Module.

Handles centralized event logging and external alerting (e.g., Discord)
by detecting system logs, exception events, and threshold violations.
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from typing import Dict, Optional

import httpx

from backend.config import AlertConfig


class ObsEvent(str, Enum):
    """
    관측성(Observability) 시스템 전반에서 사용되는 표준 이벤트 이름 정의.

    자유 형식의 로깅 문자열을 파싱하는 대신, ELK/Datadog 등의 대시보드와
    알림 규칙(Rule Engine)이 명확한 기준표를 가질 수 있도록 중앙화된 구조를 제공합니다.

    Standard event names used across the observability system.

    Provides a centralized structure so that dashboards (like ELK/Datadog)
    and rule engines have clear references, instead of parsing free-form logs.
    """

    FINETUNE_RESERVED_REDIS_KEY_VIOLATION = "reserved_redis_keys_in_extra_fields"


class ObsMetaTag(str, Enum):
    """
    관측성 시스템 전반에서 사용되는 메타데이터 플래그 모음.

    네임스페이스(meta_)를 부착하여 비즈니스 데이터와 시스템 제어용 데이터를 분리합니다.

    Collection of metadata flags used across the observability system.

    Attaches a namespace (`meta_`) to separate business data from system control data.
    """

    INTENTIONAL_WARNING = "meta_intentional_warning"


class DiscordAlertHandler(logging.Handler):
    """
    특정 조건의 로그를 Discord 웹훅으로 전송하는 커스텀 로깅 핸들러.

    [OBS] 태그가 포함되거나 ERROR 레벨 이상인 로그를 감지하여 비동기로 전송합니다.
    중복 알림 방지(Throttling)를 지원합니다.

    Custom logging handler that sends specific logs to a Discord webhook.

    Detects logs with the [OBS] tag or at ERROR level and above, sending them
    asynchronously. Supports alert deduplication (throttling).
    """

    def __init__(self, webhook_url: Optional[str] = None):
        """
        DiscordAlertHandler 초기화.

        Initializes the DiscordAlertHandler.

        Args:
            webhook_url (Optional[str]): 사용할 Discord 웹훅 URL.
                지정하지 않으면 `AlertConfig.DISCORD_WEBHOOK_URL`을 기본값으로 사용합니다.
                The Discord webhook URL to use.
                If not specified, defaults to `AlertConfig.DISCORD_WEBHOOK_URL`.
        """
        super().__init__()
        self.webhook_url = webhook_url or AlertConfig.DISCORD_WEBHOOK_URL
        self.last_alerts: Dict[str, float] = {}
        self.throttle_seconds = AlertConfig.DEFAULT_THROTTLE_SECONDS

        # [Fix] 스레드 동시성 제어 및 스레드 폭주 방지를 위한 Lock & ThreadPool 적용
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=3, thread_name_prefix="DiscordAlerter"
        )

    def emit(self, record: logging.LogRecord):
        """
        로깅 레코드를 평가하여 조건에 맞으면 Discord 알림을 트리거합니다.

        중복 알림(Throttling) 및 스레드 동시성을 고려하여 안전하게 처리합니다.

        Evaluates the logging record and triggers a Discord alert if conditions are met.

        Safely handles duplicate alerts (throttling) and thread concurrency.

        Args:
            record (logging.LogRecord): 평가할 로그 레코드 객체.
                The log record object to evaluate.
        """
        # 1. 대상 필터링: [OBS] 태그 체크 또는 ERROR 레벨 이상
        message = self.format(record)
        is_obs = "[OBS]" in message
        is_critical = record.levelno >= logging.ERROR

        if not (is_obs or is_critical):
            return

        # 2. 알림 임계값(Throttling) 체크 (포맷이 적용된 최종 메시지 기준)
        # record.msg 대신 getMessage()를 사용하여 파라미터가 포맷팅된 실제 내용을 기준으로 필터링
        alert_key = f"{record.levelno}:{record.getMessage()}"
        current_time = time.monotonic()

        # [Fix] 동시 접속(Concurrent logging) 시 last_alerts 딕셔너리 Race Condition 방어
        with self._lock:
            # [Fix] 메모리 누수 방지(Eviction Strategy): 저장된 키가 1000개를 초과하면 만료된 데이터 정리
            if len(self.last_alerts) > 1000:
                stale_keys = [
                    k
                    for k, v in self.last_alerts.items()
                    if current_time - v >= self.throttle_seconds
                ]
                for k in stale_keys:
                    del self.last_alerts[k]

            if (
                alert_key in self.last_alerts
                and current_time - self.last_alerts[alert_key] < self.throttle_seconds
            ):
                return
            # 3. 알림 발송 시간 갱신
            self.last_alerts[alert_key] = current_time

        # [Fix] 에러 폭주 시 과도한 스레드 생성을 막기 위해 ThreadPoolExecutor 사용
        self._executor.submit(self._send_discord_alert, message, record)

    def _send_discord_alert(self, formatted_message: str, record: logging.LogRecord):
        """
        실제로 HTTP 요청을 통해 Discord 웹훅에 메시지를 전송합니다.

        로그 레벨에 따라 색상을 다르게 표시하며 예외(Stack Trace) 정보가 있다면 첨부합니다.

        Actually sends the message to the Discord webhook via HTTP request.

        Displays different colors based on the log level and attaches
        exception (Stack Trace) information if available.

        Args:
            formatted_message (str): 텍스트 포맷팅이 완료된 최종 로그 문자열.
                The final log string with text formatting applied.
            record (logging.LogRecord): 원본 로그 레코드 (레벨 및 시간 참조용).
                The original log record (used for level and timestamp reference).
        """
        if not self.webhook_url:
            return

        # Discord Embed 색상 결정
        color = AlertConfig.COLOR_INFO
        if record.levelno >= logging.ERROR:
            color = AlertConfig.COLOR_CRITICAL
        elif record.levelno >= logging.WARNING:
            color = AlertConfig.COLOR_WARNING

        # Embed 데이터 구성
        embed = {
            "title": f"🚨 System Alert ({record.levelname})",
            "description": formatted_message[:2000],  # Discord 제한
            "color": color,
            "fields": [
                {
                    "name": "Location",
                    "value": f"{record.pathname}:{record.lineno}",
                    "inline": True,
                },
                {
                    "name": "Timestamp",
                    "value": time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.gmtime(record.created)
                    ),
                    "inline": True,
                },
            ],
            "footer": {"text": "FlowNote MVP Observability Pipeline"},
        }

        # 스택 트레이스가 있을 경우 추가
        if record.exc_info:
            import traceback

            exc_text = "".join(traceback.format_exception(*record.exc_info))
            embed["fields"].append(
                {
                    "name": "Stack Trace",
                    "value": f"```python\n{exc_text[:1000]}\n```",
                    "inline": False,
                }
            )

        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.post(self.webhook_url, json={"embeds": [embed]})
                if response.status_code != 204:
                    print(f"Failed to send Discord alert: {response.text}")
        except Exception as e:
            # 로그 핸들러 내부에서 발생한 에러이므로 재로깅하지 않고 표준 출력만
            print(f"Error in DiscordAlertHandler: {e}")

    def close(self):
        """
        로깅 시스템 종료 시 ThreadPoolExecutor의 자원을 안전하게 회수합니다 (Shutdown Hook).

        대기 중인 알림 전송 태스크가 완료될 때까지 대기(Best-effort)합니다.

        Safely reclaims ThreadPoolExecutor resources upon logging system shutdown.

        Waits on a best-effort basis for pending alert tasks to complete.
        """
        if hasattr(self, "_executor"):
            # 최대한 생성된 알림 전송 태스크가 완료되도록 대기 (Best-effort delivery)
            self._executor.shutdown(wait=True)
        super().close()
