# backend/graph/notifications.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase 4-4 (3단계): 연결 추천 알림 생성 및 전송 로직
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# 설계 원칙:
#   - 단일 책임 — 알림 메시지 생성과 전송 채널(채널별 어댑터)을 분리.
#   - 확장 가능 — 현재는 로그 기반 알림(in-process log)만 구현하며,
#                 향후 WebSocket Push / Email / Slack 등을 채널 어댑터로 추가 가능.
#   - 하드코딩 금지 — 알림 메시지 템플릿은 상수로 관리.
#   - PII 보안 — 알림 메시지에 user_id 원문이 포함되지 않도록 user_id_hash만 사용.
#   - 테넌트 격리 — 알림 전송 시 대상 사용자(user_id_hash) 컨텍스트를 명시.
#
# [알림 채널 확장 가이드]
#   현재: _send_log_notification() — 구조화된 로그 기록 (운영 모니터링용)
#   향후 채널 추가 시:
#     1. _send_<채널명>_notification(notification: LinkNotification) -> None 함수 추가
#     2. send_link_recommendations() 내 채널 선택 로직에 추가
#     3. 환경 변수(NOTIFICATION_CHANNEL)로 채널 전환 가능하게 구성 권장
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from __future__ import annotations

import logging
from typing import Sequence

from backend.schemas.graph import LinkNotification, LinkRecommendation

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
# 메시지 템플릿 상수 (하드코딩 금지 — 이곳에서만 관리)
# ─────────────────────────────────────────

_NOTIFICATION_TITLE_TEMPLATE = "연결 추천: {orphan_label}과(와) {candidate_label}을(를) 연결해 보시겠어요?"
_NOTIFICATION_BODY_TEMPLATE = (
    "'{orphan_label}' 노트가 고립되어 있습니다. "
    "'{candidate_label}'과(와) {similarity_pct}% 연관성이 있는 것으로 분석되었습니다. "
    "이 두 노트를 연결(Link)해 보는 건 어떨까요?"
)

# ─────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────


def _build_notification(recommendation: LinkRecommendation) -> LinkNotification:
    """
    LinkRecommendation으로부터 사용자에게 표시할 LinkNotification을 생성한다.

    Args:
        recommendation: 단일 연결 추천 쌍 정보

    Returns:
        LinkNotification — 제목 및 본문이 포함된 알림 객체
    """
    similarity_pct = round(recommendation.similarity_score * 100, 1)

    title = _NOTIFICATION_TITLE_TEMPLATE.format(
        orphan_label=recommendation.orphan_node_label,
        candidate_label=recommendation.candidate_node_label,
    )
    body = _NOTIFICATION_BODY_TEMPLATE.format(
        orphan_label=recommendation.orphan_node_label,
        candidate_label=recommendation.candidate_node_label,
        similarity_pct=similarity_pct,
    )

    return LinkNotification(
        title=title,
        body=body,
        orphan_node_id=recommendation.orphan_node_id,
        candidate_node_id=recommendation.candidate_node_id,
        similarity_score=recommendation.similarity_score,
        user_id_hash=recommendation.user_id_hash,
    )


def _send_log_notification(notification: LinkNotification) -> None:
    """
    [채널 어댑터 - Log]
    구조화된 로그로 알림을 기록한다.
    운영 모니터링 및 향후 알림 채널 구축 전 단계에서 사용한다.

    향후 WebSocket / Email / Slack 채널로 교체/병행 가능.
    """
    logger.info(
        "[GRAPH][NOTIFICATION] 연결 추천 알림 전송: user_id_hash=%s | orphan=%s | candidate=%s | score=%.4f | 제목=%s",
        notification.user_id_hash or "unassigned",
        notification.orphan_node_id[:8] if notification.orphan_node_id else "<empty>",
        notification.candidate_node_id[:8] if notification.candidate_node_id else "<empty>",
        notification.similarity_score,
        notification.title,
    )


# ─────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────


def send_link_recommendations(
    recommendations: Sequence[LinkRecommendation],
) -> list[LinkNotification]:
    """
    발굴된 연결 추천 쌍 목록을 앱 내 알림으로 전송한다.

    각 LinkRecommendation을 LinkNotification으로 변환한 후,
    현재 구성된 알림 채널(기본: 로그)로 전송한다.

    [알림 채널 현황]
    - 현재 구현: 구조화된 로그 기록 (_send_log_notification)
    - 향후 확장: WebSocket Push, Email, Slack 등 채널 어댑터 추가 예정

    [PII 보안]
    알림 메시지에는 user_id 원문이 포함되지 않으며,
    user_id_hash(mask_pii_id 결과)만 전송된다.

    [테넌트 격리 계약]
    이 함수는 이미 테넌트 격리된 recommendations를 입력으로 받는다.
    각 LinkRecommendation의 user_id_hash는 호출 측에서 격리 보장 필요.

    Args:
        recommendations: 전송할 연결 추천 쌍 목록

    Returns:
        전송된 LinkNotification 목록. 빈 입력 시 빈 리스트 반환.
    """
    if not recommendations:
        logger.debug("[GRAPH][NOTIFICATION] 전송할 추천 알림이 없습니다.")
        return []

    sent_notifications: list[LinkNotification] = []

    for rec in recommendations:
        notification = _build_notification(rec)
        _send_log_notification(notification)
        sent_notifications.append(notification)

    logger.info(
        "[GRAPH][NOTIFICATION] 연결 추천 알림 전송 완료: 총 %d건.",
        len(sent_notifications),
    )
    return sent_notifications


__all__ = ["send_link_recommendations"]
