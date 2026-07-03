# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/utils/observability.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - Observability and Alerting Module (관측성 및 알림 유틸리티).

[KO] 시스템 로그, 예외 이벤트 등을 감지하여 중앙 집중형 로깅 및 외부 알림(Discord 등)을 처리합니다.
[EN] Handles centralized event logging and external alerting (e.g., Discord) by detecting system logs and exception events.
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
    Standard event names for the observability system (표준 관측성 이벤트 이름).

    [KO] 모니터링 대시보드(ELK 등)와 알림 규칙 엔진에서 사용할 수 있도록 중앙화된 이벤트 식별자를 제공합니다.
    [EN] Provides centralized event identifiers for monitoring dashboards (e.g., ELK) and alert rule engines.
    """

    FINETUNE_RESERVED_REDIS_KEY_VIOLATION = "reserved_redis_keys_in_extra_fields"


class ObsMetaTag(str, Enum):
    """
    Metadata flags for the observability system (관측성 메타데이터 태그).

    [KO] `meta_` 네임스페이스를 사용하여 시스템 제어용 데이터를 비즈니스 데이터와 분리합니다.
    [EN] Uses the `meta_` namespace to separate system control data from business data.
    """

    INTENTIONAL_WARNING = "meta_intentional_warning"


class DiscordAlertHandler(logging.Handler):
    """
    Discord Webhook Alert Handler (Discord 알림 전송 핸들러).

    [KO] `[OBS]` 태그가 포함되거나 ERROR 레벨 이상인 로그를 감지하여 비동기로 전송합니다.
    [EN] Detects logs with the `[OBS]` tag or at ERROR level and above, sending them asynchronously.

    Throttling Semantics (알림 제한 규칙):
    - Key: `f"{record.levelno}:{record.getMessage()}"` (Per log level and unformatted content).
    - Window: `throttle_seconds` (Default: AlertConfig.DEFAULT_THROTTLE_SECONDS).
    - Behavior: Suppresses duplicate alerts within the same time window to prevent spam.
    """

    def __init__(self, webhook_url: Optional[str] = None):
        """
        [KO] 핸들러 및 Throttling 제어 상태를 초기화합니다.
        [EN] Initializes the handler and its throttling control state.

        Args:
            webhook_url: Discord webhook URL. (Default: AlertConfig.DISCORD_WEBHOOK_URL)
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
        [KO] 로그 레코드를 평가하여 Throttling 규칙 통과 시 Discord 알림을 트리거합니다.
        [EN] Evaluates the log record and triggers a Discord alert if it passes throttling rules.
        """
        # 1. 대상 필터링: [OBS] 태그 체크 또는 ERROR 레벨 이상
        message = self.format(record)
        is_obs = "[OBS]" in message
        is_critical = record.levelno >= logging.ERROR

        if not (is_obs or is_critical):
            return

        # 2. 알림 임계값(Throttling) 체크
        # record.msg 대신 getMessage()를 사용하여 파라미터가 포맷팅된 내용 기준으로 필터링
        # (formatted_message를 쓰면 타임스탬프 등 가변 데이터 때문에 중복 제거가 안됨)
        alert_key = f"{record.levelno}:{record.getMessage()}"
        current_time = time.monotonic()

        with self._lock:
            # 메모리 누수 방지(Eviction Strategy)
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

        # 에러 폭주 시 과도한 스레드 생성을 막기 위해 ThreadPoolExecutor 사용
        self._executor.submit(self._send_discord_alert, message, record)

    def _send_discord_alert(self, formatted_message: str, record: logging.LogRecord):
        """
        [KO] HTTP 통신을 통해 구성된 Embed 데이터를 Discord 웹훅으로 전송합니다.
        [EN] Sends the constructed Embed data to the Discord webhook via HTTP request.
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
        [KO] 로깅 시스템 종료 시 ThreadPool 자원을 회수하며(Shutdown Hook), 부모 핸들러의 close()를 호출합니다.
        [EN] Reclaims ThreadPool resources on system shutdown and calls the parent handler's close().
        """
        if hasattr(self, "_executor"):
            # 최대한 생성된 알림 전송 태스크가 완료되도록 대기 (Best-effort delivery)
            self._executor.shutdown(wait=True)
        super().close()
