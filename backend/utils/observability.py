# backend/utils/observability.py

import logging
import time
import threading
import httpx
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

    def emit(self, record: logging.LogRecord):
        # 1. 대상 필터링: [OBS] 태그 체크 또는 ERROR 레벨 이상
        message = self.format(record)
        is_obs = "[OBS]" in message
        is_critical = record.levelno >= logging.ERROR

        if not (is_obs or is_critical):
            return

        # 2. 알림 임계값(Throttling) 체크 (메시지 원본 기준)
        alert_key = f"{record.levelno}:{record.msg}"
        current_time = time.time()

        if alert_key in self.last_alerts:
            if current_time - self.last_alerts[alert_key] < self.throttle_seconds:
                return

        # 3. 알림 발송 트리거
        self.last_alerts[alert_key] = current_time

        # 메인 루프를 방해하지 않도록 별도 스레드에서 발송
        threading.Thread(
            target=self._send_discord_alert, args=(message, record), daemon=True
        ).start()

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
