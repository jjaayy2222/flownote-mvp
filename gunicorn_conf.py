# gunicorn_conf.py
import multiprocessing
import os

# ------------------------------------------------------------------------------
# Gunicorn Configuration for Production
# ------------------------------------------------------------------------------

# 바인딩 주소 (환경변수 PORT 사용, 기본값 8000)
port = os.getenv("PORT", "8000")
bind = f"0.0.0.0:{port}"

# 워커 설정
# CPU 코어 수 * 2 + 1 (일반적인 권장값)
# 하지만 메모리 제한이 있는 클라우드 환경(Railway/Render Starter)에서는 2~4개로 제한하는 것이 좋음
workers = int(os.getenv("WEB_CONCURRENCY", 2))

# 워커 클래스 (FastAPI/ASGI 실행을 위해 필수)
worker_class = "uvicorn.workers.UvicornWorker"

# 타임아웃 설정
# LLM 처리(OpenAI API 호출 등)가 오래 걸릴 수 있으므로 넉넉하게 설정 (기본 30초 -> 120초)
timeout = 120
keepalive = 5

# 로깅 설정
accesslog = "-"  # stdout
errorlog = "-"  # stderr
loglevel = "info"

# 프로세스 이름
proc_name = "flownote-api"

# 워커 재시작 설정 (메모리 누수 방지)
max_requests = 1000
max_requests_jitter = 50

print(f"🚀 Gunicorn starting on {bind} with {workers} workers (timeout: {timeout}s)")
