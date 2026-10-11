# tests/unit/test_deps_auth.py

"""
Unit tests for authentication dependency and JWT token verification (backend/api/deps.py).
Tests token creation, decoding, expiration handling, error responses, and environment routing.
"""

import datetime
from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException, WebSocketException, status

from backend.api.deps import (
    _ensure_dev_environment,
    create_access_token,
    get_current_user,
    get_current_user_ws,
    verify_token,
)
from backend.config import AppConfig, AuthConfig


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

        # "Bearer " 접두사 포함 검증
        user = verify_token(f"Bearer {token}")
        assert user["id"] == 99
        assert user["username"] == "prefixed_user"
        assert user["role"] == "user"

        # 소문자 "bearer " 접두사 포함 검증
        user_lower = verify_token(f"bearer {token}")
        assert user_lower["id"] == 99

    def test_verify_token_expired(self):
        """만료된 토큰 검증 시 401 및 명확한 오류 메시지 반환 검증."""
        payload = {"id": 1, "username": "expired_user"}
        # 과거 시간으로 만료된 토큰 생성
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
        # 다른 비밀키로 서명된 토큰 수동 생성
        now = datetime.datetime.now(datetime.timezone.utc)
        payload = {
            "sub": "2",
            "username": "attacker",
            "role": "user",
            "exp": now + datetime.timedelta(minutes=30),
            "iat": now,
        }
        tampered_token = jwt.encode(
            payload, "wrong-secret-key-12345", algorithm="HS256"
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


class TestFastAPIDependencies:
    """FastAPI HTTP 및 WebSocket 의존성(get_current_user, get_current_user_ws) 테스트."""

    def test_get_current_user_http_dependency(self):
        """get_current_user가 유효한 토큰으로부터 사용자 정보를 정상 반환하는지 확인."""
        payload = {"id": 1, "username": "admin_user", "role": "admin"}
        token = create_access_token(payload)

        user = get_current_user(token=token)
        assert user["username"] == "admin_user"
        assert user["role"] == "admin"

    @pytest.mark.asyncio
    async def test_get_current_user_ws_valid_token(self):
        """WebSocket 연결 시 쿼리 파라미터 유효 토큰으로 사용자 반환 검증."""
        payload = {"id": 2, "username": "ws_user", "role": "user"}
        token = create_access_token(payload)
        mock_ws = MagicMock()

        user = await get_current_user_ws(websocket=mock_ws, token=token)
        assert user["id"] == 2
        assert user["username"] == "ws_user"

    @pytest.mark.asyncio
    async def test_get_current_user_ws_missing_token(self):
        """WebSocket 연결 시 토큰 파라미터 누락인 경우 1008 Policy Violation 발생 확인."""
        mock_ws = MagicMock()

        with pytest.raises(WebSocketException) as exc_info:
            await get_current_user_ws(websocket=mock_ws, token=None)

        assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION
        assert (
            exc_info.value.reason == "Missing authentication token via query parameter"
        )

    @pytest.mark.asyncio
    async def test_get_current_user_ws_invalid_token(self):
        """WebSocket 연결 시 유효하지 않은 토큰 전달 시 1008 Policy Violation 발생 확인."""
        mock_ws = MagicMock()

        with pytest.raises(WebSocketException) as exc_info:
            await get_current_user_ws(websocket=mock_ws, token="invalid-token")

        assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION


class TestAppConfigEnvironmentRouting:
    """AppConfig 환경 라우팅 및 _ensure_dev_environment 단위 테스트."""

    def test_app_config_environment_detection(self):
        """AppConfig의 get_environment 및 is_dev_environment 동작 확인."""
        with patch.object(AppConfig, "get_environment", return_value="production"):
            assert AppConfig.is_dev_environment() is False

        with patch.object(AppConfig, "get_environment", return_value="development"):
            assert AppConfig.is_dev_environment() is True

        with patch.object(AppConfig, "get_environment", return_value="local"):
            assert AppConfig.is_dev_environment() is True

        with patch.object(AppConfig, "get_environment", return_value="test"):
            assert AppConfig.is_dev_environment() is True

    def test_ensure_dev_environment_raises_in_production(self):
        """_ensure_dev_environment가 비개발(production) 환경에서 예외를 발생시키는지 검증."""
        with patch.object(AppConfig, "is_dev_environment", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                _ensure_dev_environment(
                    lambda: HTTPException(
                        status_code=403, detail="Forbidden in production"
                    )
                )
            assert exc_info.value.status_code == 403

    def test_ensure_dev_environment_passes_in_dev(self):
        """_ensure_dev_environment가 개발/로컬 환경에서는 통과하는지 검증."""
        with patch.object(AppConfig, "is_dev_environment", return_value=True):
            # 예외가 발생하지 않아야 함
            _ensure_dev_environment(
                lambda: HTTPException(status_code=403, detail="Error")
            )
