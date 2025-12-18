# README 업데이트 작업 (Phase 4)

> **목적**: Phase 4 Celery 자동화 시스템 관련 README 업데이트 내용  
> **상태**: 작성 완료, README.md 병합 대기

---

## 📋 업데이트 내용

### 1. Celery 실행 방법

#### Celery Worker 실행

```bash
# 개발 환경
celery -A backend.celery_app.celery worker --loglevel=info

# 프로덕션 환경 (데몬 모드)
celery -A backend.celery_app.celery worker --loglevel=warning --detach
```

**Worker 옵션 설명**:
- `--loglevel=info`: 로그 레벨 설정 (debug, info, warning, error, critical)
- `--concurrency=4`: 동시 실행 워커 수 (기본값: CPU 코어 수)
- `--max-tasks-per-child=1000`: 워커 재시작 전 최대 작업 수
- `--detach`: 백그라운드 실행

#### Celery Beat 실행 (스케줄러)

```bash
# 개발 환경
celery -A backend.celery_app.celery beat --loglevel=info

# 프로덕션 환경
celery -A backend.celery_app.celery beat --loglevel=warning --detach
```

**Beat 스케줄**:
- 매일 00:00 - 일일 재분류
- 매주 일요일 00:00 - 주간 재분류
- 매주 일요일 02:00 - 자동 아카이브
- 매주 월요일 08:00 - 주간 리포트
- 매월 1일 10:00 - 월간 리포트
- 매 10분 - 동기화 상태 확인
- 매일 03:00 - 로그 정리

#### 통합 실행 (Worker + Beat)

```bash
# 개발 환경 (하나의 프로세스로 실행)
celery -A backend.celery_app.celery worker --beat --loglevel=info
```

> **⚠️ 주의**: 프로덕션 환경에서는 Worker와 Beat를 **별도 프로세스**로 실행하는 것을 권장합니다.

---

### 2. Redis 설정 가이드

#### Redis 설치

**macOS (Homebrew)**:
```bash
brew install redis
brew services start redis
```

**Ubuntu/Debian**:
```bash
sudo apt-get update
sudo apt-get install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

**Docker**:
```bash
docker run -d -p 6379:6379 --name flownote-redis redis:7-alpine
```

#### Redis 연결 확인

```bash
# Redis CLI로 연결 테스트
redis-cli ping
# 응답: PONG

# 연결 정보 확인
redis-cli info server
```

#### 환경 변수 설정

`.env` 파일에 다음 내용을 추가하세요:

```bash
# Redis 설정
REDIS_URL=redis://localhost:6379/0

# Celery 설정 (선택사항)
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
CELERY_TIMEZONE=Asia/Seoul
```

**Redis URL 형식**:
```
redis://[username:password@]host:port/db_number
```

**예시**:
- 로컬 개발: `redis://localhost:6379/0`
- 비밀번호 사용: `redis://:mypassword@localhost:6379/0`
- 원격 서버: `redis://redis.example.com:6379/0`

#### Redis 설정 파일 (선택사항)

프로덕션 환경에서는 `/etc/redis/redis.conf` 파일을 수정하여 보안 및 성능을 최적화할 수 있습니다:

```conf
# 비밀번호 설정
requirepass your_strong_password_here

# 최대 메모리 설정 (예: 256MB)
maxmemory 256mb
maxmemory-policy allkeys-lru

# 영속성 설정 (RDB 스냅샷)
save 900 1
save 300 10
save 60 10000

# 로그 파일
logfile /var/log/redis/redis-server.log
```

---

### 3. Flower 모니터링 사용법

#### Flower 설치 및 실행

Flower는 Celery 작업을 모니터링하는 웹 기반 도구입니다.

**설치** (이미 `requirements.txt`에 포함):
```bash
pip install flower==2.0.1
```

**실행**:
```bash
# 기본 실행 (포트 5555)
celery -A backend.celery_app.celery flower

# 커스텀 포트
celery -A backend.celery_app.celery flower --port=5555

# 인증 활성화
celery -A backend.celery_app.celery flower --basic_auth=admin:password

# 프로덕션 환경 (백그라운드)
celery -A backend.celery_app.celery flower --port=5555 --basic_auth=admin:password &
```

#### Flower 접속

브라우저에서 다음 URL로 접속:
```
http://localhost:5555
```

#### Flower 주요 기능

1. **대시보드**:
   - 실시간 작업 상태 (성공/실패/진행 중)
   - 워커 상태 및 리소스 사용량
   - 작업 처리 속도 그래프

2. **작업 목록**:
   - 실행 중/완료/실패한 작업 조회
   - 작업 상세 정보 (인자, 결과, 실행 시간)
   - 작업 재시도 및 취소

3. **워커 관리**:
   - 워커 목록 및 상태
   - 워커별 작업 할당 현황
   - 워커 재시작/종료

4. **브로커 모니터링**:
   - Redis 연결 상태
   - 큐 길이 및 대기 작업 수

#### Flower 환경 변수

`.env` 파일에 추가:

```bash
# Flower 설정
FLOWER_PORT=5555
FLOWER_BASIC_AUTH=admin:your_secure_password
FLOWER_URL_PREFIX=/flower  # Nginx 리버스 프록시 사용 시
```

#### Nginx 리버스 프록시 설정 (선택사항)

```nginx
location /flower/ {
    proxy_pass http://localhost:5555/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

---

## 🚀 빠른 시작 가이드

### 1. Redis 시작

```bash
# macOS
brew services start redis

# Linux
sudo systemctl start redis-server

# Docker
docker run -d -p 6379:6379 --name flownote-redis redis:7-alpine
```

### 2. 환경 변수 설정

`.env` 파일 생성:
```bash
REDIS_URL=redis://localhost:6379/0
```

### 3. Celery Worker 및 Beat 실행

**터미널 1 - Worker**:
```bash
celery -A backend.celery_app.celery worker --loglevel=info
```

**터미널 2 - Beat**:
```bash
celery -A backend.celery_app.celery beat --loglevel=info
```

**터미널 3 - Flower (선택사항)**:
```bash
celery -A backend.celery_app.celery flower --port=5555
```

### 4. FastAPI 서버 실행

**터미널 4 - API 서버**:
```bash
uvicorn backend.main:app --reload --port 8000
```

### 5. 동작 확인

- **API 문서**: http://localhost:8000/docs
- **Flower 대시보드**: http://localhost:5555
- **자동화 로그 조회**: http://localhost:8000/api/automation/logs

---

## 🔧 트러블슈팅

### Redis 연결 실패

**증상**:
```
kombu.exceptions.OperationalError: Error 61 connecting to localhost:6379. Connection refused.
```

**해결 방법**:
1. Redis 실행 확인: `redis-cli ping`
2. Redis 재시작: `brew services restart redis` (macOS)
3. 포트 확인: `lsof -i :6379`

### Celery Worker 시작 실패

**증상**:
```
ImportError: No module named 'backend.celery_app.celery'
```

**해결 방법**:
1. PYTHONPATH 확인: `echo $PYTHONPATH`
2. 프로젝트 루트에서 실행: `cd /path/to/flownote-mvp`
3. 가상 환경 활성화 확인: `which python`

### Beat 스케줄 미실행

**증상**:
- 정해진 시간에 작업이 실행되지 않음

**해결 방법**:
1. Beat 프로세스 실행 확인
2. 타임존 설정 확인: `CELERY_TIMEZONE=Asia/Seoul`
3. Beat 로그 확인: `celery -A backend.celery_app.celery beat --loglevel=debug`

### Flower 접속 불가

**증상**:
- `http://localhost:5555` 접속 실패

**해결 방법**:
1. Flower 프로세스 실행 확인: `ps aux | grep flower`
2. 포트 충돌 확인: `lsof -i :5555`
3. 방화벽 설정 확인

---

## 📚 추가 참고 자료

- [Celery 공식 문서](https://docs.celeryproject.org/)
- [Redis 공식 문서](https://redis.io/documentation)
- [Flower 공식 문서](https://flower.readthedocs.io/)
- [Automation API 문서](./automation_api_documentation.md)

---

> **작성일**: 2025-12-16  
> **작성자**: Jay  
> **상태**: README.md 병합 대기
