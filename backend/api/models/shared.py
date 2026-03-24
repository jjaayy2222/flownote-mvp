# backend/api/models/shared.py

from typing import Literal

# ---------------------------------------------------------
# Shared Types
# ---------------------------------------------------------
ApiStatus = Literal["success", "error"]
SuccessStatus = Literal[
    "success"
]  # API가 항상 성공 객체만 반환하는 명시적 응답 컨트랙트용
FeedbackRating = Literal["up", "down", "none"]

# ---------------------------------------------------------
# OpenAPI/Swagger Field Descriptions
# ---------------------------------------------------------
API_STATUS_DESC = "API 응답 상태 ('success' 또는 'error')"
SUCCESS_STATUS_DESC = "API 성공 응답 상태 ('success')"
FEEDBACK_RATING_DESC = "피드백 평가 값 ('up', 'down', 'none')"
API_MESSAGE_DESC = "API 반환 메시지"
