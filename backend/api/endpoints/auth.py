# backend/api/endpoints/auth.py

"""
Authentication & Token Issuance Endpoint
Provides standard JWT token issuance for API clients and automated tests.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.api.deps import create_access_token
from backend.config import AuthConfig

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Authentication"])


class TokenRequest(BaseModel):
    """토큰 발급 요청 페이로드"""

    username: str = Field(
        ..., min_length=1, max_length=100, description="사용자 식별자"
    )
    role: Optional[str] = Field(
        default="user", max_length=50, description="사용자 권한 역할"
    )
    client_id: Optional[str] = Field(
        default=None, description="선택적 클라이언트 식별자"
    )


class TokenResponse(BaseModel):
    """표준 JWT 액세스 토큰 응답 스키마"""

    access_token: str = Field(..., description="서명된 JWT 액세스 토큰")
    token_type: str = Field(default="bearer", description="토큰 유형")
    expires_in: int = Field(..., description="토큰 유효 기간 (초)")


@router.post(
    "/auth/token",
    response_model=TokenResponse,
    summary="JWT 액세스 토큰 발급",
    description="제공된 사용자 식별자 정보를 기반으로 서명된 JWT Bearer 액세스 토큰을 발급합니다.",
)
@router.post(
    "/token",
    response_model=TokenResponse,
    summary="OAuth2 표준 /token 엔드포인트",
    include_in_schema=False,
)
async def issue_access_token(request: TokenRequest) -> TokenResponse:
    """
    클라이언트를 위한 JWT 액세스 토큰 발급 핸들러.

    운영 환경 및 개발 환경 모두에서 안전하게 토큰을 발급하며,
    로그에는 사용자 식별자 원문을 남기지 않고 발급 성공 여부만 기록합니다.
    """
    secret = AuthConfig.get_jwt_secret()
    if not secret:
        logger.error(
            "Token issuance failed: JWT_SECRET_KEY is not configured on server."
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service is not properly configured.",
        )

    # 기본 클레임 구성
    token_claims = {
        "sub": request.username,
        "username": request.username,
        "role": request.role or "user",
    }

    token = create_access_token(token_claims)
    expire_minutes = AuthConfig.get_access_token_expire_minutes()

    logger.info("Successfully issued access token (Role: %s)", token_claims["role"])

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expire_minutes * 60,
    )
