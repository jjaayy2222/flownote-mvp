# backend/utils/observability.py

import logging
import time
import threading
import httpx
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, Any
from backend.config import AlertConfig


class DiscordAlertHandler(logging.Handler):
    """
    [OBS] 태그가 포함된 로그를 감지하여 Discord로 전송하는 커스텀 로깅 핸들러.
    - 중복 알림 방지(Throttling) 및 비동기 발송 지원.
    """

    def __init__(self, webhook_url: Optional[str] = None):
        super().__init__()
        self.webhook_url = webhook_url or AlertConfig.DISCORD_WEBHOOK_URL
        self.last_alerts: Dict[str, float] = {}
        self.throttle_seconds = AlertConfig.DEFAULT_THROTTLE_SECONDS
        
        # [Fix] 스레드 동시성 제어 및 스레드 폭주 방지를 위한 Lock & ThreadPool 적용
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="DiscordAlerter")


    def emit(self, record: logging.LogRecord):
        # 1. 대상 필터링: [OBS] 태그 체크 또는 ERROR 레벨 이상
        message = self.format(record)
        is_obs = "[OBS]" in message
        is_critical = record.levelno >= logging.ERROR

        if not (is_obs or is_critical):
            return

        # 2. 알림 임계값(Throttling) 체크 (포맷이 적용된 최종 메시지 기준)
        # record.msg 대신 getMessage()를 사용하여 파라미터가 포맷팅된 실제 내용을 기준으로 필터링
        alert_key = f"{record.levelno}:{record.getMessage()}"
        current_time = time.time()

        # [Fix] 동시 접속(Concurrent logging) 시 last_alerts 딕셔너리 Race Condition 방어
        with self._lock:
            # [Fix] 메모리 누수 방지(Eviction Strategy): 저장된 키가 1000개를 초과하면 만료된 데이터 정리
            if len(self.last_alerts) > 1000:
                stale_keys = [k for k, v in self.last_alerts.items() if current_time - v >= self.throttle_seconds]
                for k in stale_keys:
                    del self.last_alerts[k]

            if alert_key in self.last_alerts:
                if current_time - self.last_alerts[alert_key] < self.throttle_seconds:
                    return
            # 3. 알림 발송 시간 갱신
            self.last_alerts[alert_key] = current_time

        # [Fix] 에러 폭주 시 과도한 스레드 생성을 막기 위해 ThreadPoolExecutor 사용
        self._executor.submit(self._send_discord_alert, message, record)

    def _send_discord_alert(self, formatted_message: str, record: logging.LogRecord):
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
        """로깅 시스템 종료 시 ThreadPoolExecutor의 자원을 안전하게 회수(Shutdown Hook)합니다."""
        if hasattr(self, "_executor"):
            self._executor.shutdown(wait=False)
        super().close()

