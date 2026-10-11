# tests/unit/test_deps_auth.py

"""
Unit tests for authentication dependency and JWT token verification (backend/api/deps.py).
Tests token creation, decoding, expiration handling, error responses, environment routing,
PII masking in WebSocket contexts, and token issuance endpoints.
"""

import datetime
from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException, WebSocketException, status
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from backend.api.deps import (
    _ensure_dev_environment,
    create_access_token,
    get_current_user,
    get_current_user_ws,
    verify_token,
)
from backend.config import AppConfig, AuthConfig
from backend.main import app
from backend.services.websocket_manager import ConnectionManager, UserContext


class TestJWTTokenVerification:
    """JWT 토큰 생성 및 검증(verify_token) 단위 테스트."""

    def test_create_and_verify_token_roundtrip(self):
        """토큰 생성 후 정상 디코딩 및 사용자 정보 추출 확인."""
        payload = {"id": 101, "username": "test_developer", "role": "admin"}
        token = create_access_token(payload)

        user = verify_token(token)

        assert user["id"] == 101
        assert user["username"] == "test_developer"
        assert user["role"] == "admin"

    def test_verify_token_bearer_prefix(self):
        """Bearer 접두사가 포함된 토큰도 정상적으로 파싱되는지 검증."""
        payload = {"sub": "99", "username": "prefixed_user", "role": "user"}
        token = create_access_token(payload)

        user = verify_token(f"Bearer {token}")
        assert user["id"] == 99
        assert user["username"] == "prefixed_user"
        assert user["role"] == "user"

        user_lower = verify_token(f"bearer {token}")
        assert user_lower["id"] == 99

    def test_verify_token_expired(self):
        """만료된 토큰 검증 시 401 및 명확한 오류 메시지 반환 검증."""
        payload = {"id": 1, "username": "expired_user"}
        expired_token = create_access_token(
            payload, expires_delta=datetime.timedelta(seconds=-60)
        )

        with pytest.raises(HTTPException) as exc_info:
            verify_token(expired_token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Token has expired"
        assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}

    def test_verify_token_invalid_signature(self):
        """잘못된 비밀키로 서명된 토큰 검증 시 401 반환 검증."""
        now = datetime.datetime.now(datetime.timezone.utc)
        payload = {
            "sub": "2",
            "username": "attacker",
            "role": "user",
            "exp": now + datetime.timedelta(minutes=30),
            "iat": now,
        }
        tampered_token = jwt.encode(
            payload, "wrong-secret-key-at-least-32-chars-long!", algorithm="HS256"
        )

        with pytest.raises(HTTPException) as exc_info:
            verify_token(tampered_token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Could not validate credentials"

    def test_verify_token_malformed(self):
        """형식이 깨진 토큰 문자열 검증 시 401 반환 검증."""
        malformed_token = "invalid.token.payload"

        with pytest.raises(HTTPException) as exc_info:
            verify_token(malformed_token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Could not validate credentials"

    def test_verify_token_empty_or_whitespace(self):
        """빈 문자열 또는 공백만 있는 토큰 검증 시 401 반환 검증."""
        for empty_val in ["", "   ", "\t\n"]:
            with pytest.raises(HTTPException) as exc_info:
                verify_token(empty_val)
            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert exc_info.value.detail == "Authentication token is missing"

    def test_verify_token_missing_subject_and_id(self):
        """사용자 식별 정보(id, sub, username)가 전혀 없는 토큰 거부 검증."""
        now = datetime.datetime.now(datetime.timezone.utc)
        payload = {
            "role": "user",
            "exp": now + datetime.timedelta(minutes=30),
            "iat": now,
        }
        secret = AuthConfig.get_jwt_secret()
        assert secret is not None
        token = jwt.encode(payload, secret, algorithm=AuthConfig.JWT_ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            verify_token(token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert (
            exc_info.value.detail
            == "Invalid token payload: missing user identification"
        )

    def test_verify_token_id_normalization(self):
        """숫자 형식의 문자열 ID가 정수형으로 정규화되는지 확인."""
        payload = {"id": "12345", "username": "number_user", "role": "user"}
        token = create_access_token(payload)

        user = verify_token(token)
        assert user["id"] == 12345
        assert isinstance(user["id"], int)

    def test_verify_token_missing_secret_key_server_error(self):
        """서버에 JWT_SECRET_KEY가 설정되지 않은 경우 500 내부 오류 반환 검증."""
        with patch.object(AuthConfig, "get_jwt_secret", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                verify_token("some.jwt.token")

            assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert exc_info.value.detail == "Authentication service configuration error"


class TestAuthConfigValidation:
    """AuthConfig 설정 검증 및 안전성 테스트 (댓글 1, 2, 5 검증)."""

    def test_validate_config_production_requires_secret(self, monkeypatch):
        """운영 환경에서 시크릿 미설정 시 ValueError 발생 확인."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        monkeypatch.delenv("SECRET_KEY", raising=False)

        with pytest.raises(
            ValueError, match="CRITICAL: JWT_SECRET_KEY.*is required in production"
        ):
            AuthConfig.validate_config()

    def test_validate_config_production_rejects_short_secret(self, monkeypatch):
        """운영 환경에서 32자 미만 시크릿 거부 확인."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("JWT_SECRET_KEY", "short-secret-123")

        with pytest.raises(ValueError, match="too short"):
            AuthConfig.validate_config()

    def test_validate_config_production_rejects_insecure_placeholder(self, monkeypatch):
        """운영 환경에서 기본 placeholder 및 취약한 키 거부 확인 (대소문자 무관 검사)."""
        monkeypatch.setenv("ENVIRONMENT", "production")

        # 소문자, 대문자, 혼합 대소문자 변형 모두 거부되는지 확인 (PR#1872 댓글 1)
        insecure_variations = [
            "your-secret-key-at-least-32-chars-long",
            "YOUR-SECRET-KEY-at-least-32-chars-long",
            "Your-Secret-Key-production-suffix-123456",
            "changeme-production-secret-value-longer-than-32",
        ]
        for bad_secret in insecure_variations:
            monkeypatch.setenv("JWT_SECRET_KEY", bad_secret)
            with pytest.raises(ValueError, match="known insecure placeholder"):
                AuthConfig.validate_config()

    def test_validate_config_algorithm_length_enforcement(self, monkeypatch):
        """선택된 HMAC 알고리즘에 따른 최소 키 길이 검증 (PR#1872 댓글 2, RFC 7518 §3.2)."""
        monkeypatch.setenv("ENVIRONMENT", "production")

        # HS384: 48자 요구
        monkeypatch.setenv("JWT_ALGORITHM", "HS384")
        monkeypatch.setenv(
            "JWT_SECRET_KEY", "thirty-two-chars-long-secret-key-ok!"
        )  # 35 chars < 48
        with pytest.raises(ValueError, match="too short.*HS384.*48"):
            AuthConfig.validate_config()

        # HS384: 48자 이상 통과
        monkeypatch.setenv(
            "JWT_SECRET_KEY",
            "forty-eight-chars-minimum-valid-secret-key-for-hs384-here!",
        )
        AuthConfig.validate_config()

        # HS512: 64자 요구
        monkeypatch.setenv("JWT_ALGORITHM", "HS512")
        monkeypatch.setenv(
            "JWT_SECRET_KEY",
            "forty-eight-chars-minimum-valid-secret-key-for-hs384-here!",
        )  # 58 chars < 64
        with pytest.raises(ValueError, match="too short.*HS512.*64"):
            AuthConfig.validate_config()

        # HS512: 64자 이상 통과
        monkeypatch.setenv(
            "JWT_SECRET_KEY",
            "sixty-four-chars-minimum-valid-secret-key-for-hs512-algorithm-testing-123456!",
        )
        AuthConfig.validate_config()

    def test_validate_config_rejects_unsupported_or_insecure_algorithms(
        self, monkeypatch
    ):
        """none 알고리즘 및 미지원 알고리즘 거부 확인 (CVE-2015-9235 방지)."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("JWT_SECRET_KEY", "a" * 64)

        for invalid_algo in ["none", "NONE", "RS256", "DES"]:
            monkeypatch.setenv("JWT_ALGORITHM", invalid_algo)
            with pytest.raises(
                ValueError, match="Unsupported or insecure JWT_ALGORITHM"
            ):
                AuthConfig.validate_config()

    def test_validate_config_production_accepts_strong_secret(self, monkeypatch):
        """운영 환경에서 32자 이상의 안전한 시크릿 통과 확인."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv(
            "JWT_SECRET_KEY",
            "a-very-strong-production-random-secret-key-value-9876543210!",
        )
        # 예외 없이 통과해야 함
        AuthConfig.validate_config()

    def test_safe_integer_parsing_expiration_minutes(self, monkeypatch):
        """정수가 아닌 환경 변수 값이 제공되어도 안전하게 기본값 60분 적용 확인."""
        monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "invalid_string")
        assert AuthConfig.get_access_token_expire_minutes() == 60


class TestFastAPIDependencies:
    """FastAPI HTTP 및 WebSocket 의존성(get_current_user, get_current_user_ws) 테스트."""

    def test_get_current_user_http_dependency_with_credentials(self):
        """HTTPAuthorizationCredentials 객체로 get_current_user 호출 시 정상 동작 확인."""
        payload = {"id": 1, "username": "admin_user", "role": "admin"}
        token = create_access_token(payload)

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        user = get_current_user(credentials=creds)
        assert user["username"] == "admin_user"
        assert user["role"] == "admin"

    def test_get_current_user_http_dependency_with_raw_string(self):
        """문자열 토큰을 직접 전달하여 get_current_user 호출 시 정상 동작 확인."""
        payload = {"id": 1, "username": "admin_user", "role": "admin"}
        token = create_access_token(payload)

        user = get_current_user(credentials=token)
        assert user["username"] == "admin_user"

    @pytest.mark.asyncio
    async def test_get_current_user_ws_with_authorization_header(self):
        """WebSocket 연결 시 Authorization 헤더를 통한 인증 성공 검증 (댓글 3)."""
        payload = {"id": 2, "username": "ws_user", "role": "user"}
        token = create_access_token(payload)
        mock_ws = MagicMock()
        mock_ws.query_params = {}
        mock_ws.headers = {"authorization": f"Bearer {token}"}

        user = await get_current_user_ws(
            websocket=mock_ws, authorization=f"Bearer {token}"
        )
        assert user["id"] == 2
        assert user["username"] == "ws_user"

    @pytest.mark.asyncio
    async def test_get_current_user_ws_with_sec_websocket_protocol(self):
        """WebSocket 연결 시 Sec-WebSocket-Protocol 헤더를 통한 인증 성공 검증 (댓글 3)."""
        payload = {"id": 3, "username": "protocol_user", "role": "user"}
        token = create_access_token(payload)
        mock_ws = MagicMock()
        mock_ws.query_params = {}
        mock_ws.headers = {"sec-websocket-protocol": f"access_token, {token}"}

        user = await get_current_user_ws(
            websocket=mock_ws,
            authorization=None,
            sec_websocket_protocol=f"access_token, {token}",
        )
        assert user["id"] == 3
        assert user["username"] == "protocol_user"

    @pytest.mark.asyncio
    async def test_get_current_user_ws_rejects_query_parameter_token(self):
        """URL 쿼리 파라미터로 토큰 전송 시 1008 Policy Violation으로 차단 검증 (댓글 3)."""
        mock_ws = MagicMock()
        mock_ws.query_params = {"token": "some-token-in-url"}

        with pytest.raises(WebSocketException) as exc_info:
            await get_current_user_ws(websocket=mock_ws)

        assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION
        assert (
            "Query parameter token transmission is forbidden" in exc_info.value.reason
        )

    @pytest.mark.asyncio
    async def test_get_current_user_ws_missing_header(self):
        """인증 헤더가 완전히 누락된 경우 1008 Policy Violation 발생 검증."""
        mock_ws = MagicMock()
        mock_ws.query_params = {}
        mock_ws.headers = {}

        with pytest.raises(WebSocketException) as exc_info:
            await get_current_user_ws(websocket=mock_ws, authorization=None)

        assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION
        assert exc_info.value.reason == "Missing authentication header"


class TestAppConfigEnvironmentRouting:
    """AppConfig 환경 라우팅 및 _ensure_dev_environment 단위 테스트 (댓글 7 회귀 방지)."""

    def test_app_config_environment_detection(self, monkeypatch):
        """monkeypatch를 사용하여 실제 AppConfig.get_environment()와 is_dev_environment() 검증."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        assert AppConfig.get_environment() == "production"
        assert AppConfig.is_dev_environment() is False

        monkeypatch.setenv("ENVIRONMENT", "development")
        assert AppConfig.get_environment() == "development"
        assert AppConfig.is_dev_environment() is True

        monkeypatch.setenv("ENVIRONMENT", "local")
        assert AppConfig.get_environment() == "local"
        assert AppConfig.is_dev_environment() is True

        monkeypatch.setenv("ENVIRONMENT", "test")
        assert AppConfig.get_environment() == "test"
        assert AppConfig.is_dev_environment() is True

    def test_ensure_dev_environment_raises_in_production(self, monkeypatch):
        """_ensure_dev_environment가 production 환경에서 예외를 발생시키는지 검증."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        with pytest.raises(HTTPException) as exc_info:
            _ensure_dev_environment(
                lambda: HTTPException(status_code=403, detail="Forbidden in production")
            )
        assert exc_info.value.status_code == 403

    def test_ensure_dev_environment_passes_in_dev(self, monkeypatch):
        """_ensure_dev_environment가 dev 환경에서는 통과하는지 검증."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        # 예외가 발생하지 않아야 함
        _ensure_dev_environment(lambda: HTTPException(status_code=403, detail="Error"))


class TestAuthEndpointsAndPII:
    """토큰 발급 엔드포인트 및 PII 마스킹 검증 (댓글 4, 6 검증)."""

    def test_token_issuance_endpoints(self):
        """POST /api/auth/token 및 /token 엔드포인트 토큰 발급 확인."""
        client = TestClient(app)

        # /api/auth/token
        res1 = client.post(
            "/api/auth/token",
            json={"username": "flow_tester", "role": "admin"},
        )
        assert res1.status_code == 200
        data1 = res1.json()
        assert "access_token" in data1
        assert data1["token_type"] == "bearer"
        assert data1["expires_in"] > 0

        # /token
        res2 = client.post(
            "/token",
            json={"username": "flow_tester", "role": "user"},
        )
        assert res2.status_code == 200
        data2 = res2.json()
        assert "access_token" in data2

    def test_user_context_repr_masks_pii(self):
        """UserContext의 __repr__이 사용자 ID와 이름을 마스킹하여 로그에 노출되지 않는지 검증 (댓글 6)."""
        ctx = UserContext(user_id=98765, username="secret_personal_name", role="admin")
        repr_str = repr(ctx)

        assert "98765" not in repr_str
        assert "secret_personal_name" not in repr_str
        assert "user_id=***" in repr_str
        assert "username=***" in repr_str
        assert "role='admin'" in repr_str


class TestWebSocketCloseReasonSanitization:
    """WebSocket 연결 종료 사유 정제 및 로그 안전성 단위 테스트 (PR#1872 댓글 3, CWE-117 방지)."""

    def test_sanitize_close_reason_strips_newlines_and_control_chars(self):
        """줄바꿈 및 제어 문자가 공백으로 치환되어 로그 위조(Log Injection)가 차단되는지 검증."""
        malicious_reason = (
            "normal_close\r\n2026-10-12 00:00:00 [INFO] Fake log injection line\n"
        )
        sanitized = ConnectionManager.sanitize_close_reason(malicious_reason)

        assert "\r" not in sanitized
        assert "\n" not in sanitized
        assert "normal_close" in sanitized
        assert "Fake log injection line" in sanitized

    def test_sanitize_close_reason_masks_tokens_and_emails(self):
        """개인정보(이메일, Bearer 토큰)가 로그에 노출되지 않고 마스킹되는지 검증."""
        reason_with_pii = "User test.user@example.com disconnected after using Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token"
        sanitized = ConnectionManager.sanitize_close_reason(reason_with_pii)

        assert "test.user@example.com" not in sanitized
        assert "[EMAIL_REDACTED]" in sanitized
        assert "eyJhbGciOi" not in sanitized
        assert "Bearer [REDACTED]" in sanitized

    def test_sanitize_close_reason_truncates_oversized_payloads(self):
        """과도하게 긴 종료 사유가 기본 50자로 안전하게 축약되는지 검증."""
        long_reason = "X" * 120
        sanitized = ConnectionManager.sanitize_close_reason(long_reason, max_len=50)

        assert len(sanitized) == 53  # 50자 + "..."
        assert sanitized.endswith("...")

    def test_sanitize_close_reason_null_safety(self):
        """None, 빈 문자열, 공백만 있는 경우 안전하게 'none'을 반환하는지 검증."""
        assert ConnectionManager.sanitize_close_reason(None) == "none"
        assert ConnectionManager.sanitize_close_reason("") == "none"
        assert ConnectionManager.sanitize_close_reason("   ") == "none"
        assert ConnectionManager.sanitize_close_reason("\r\n\t") == "none"
