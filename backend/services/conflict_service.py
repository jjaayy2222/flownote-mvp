# backend/services/conflict_service.py

"""
통합 분류 서비스: PARA + Keyword + Conflict Resolution

- Snapshot 기능 제거
- 매번 새로운 분류 결과 생성하기
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from backend.agent.error_utils import build_meta, log_agent_error

logger = logging.getLogger(__name__)

# 필요한 분류기 import
try:
    from backend.classifier.conflict_resolver import (
        ClassificationResult,
        ConflictResolver,
    )
    from backend.classifier.keyword import KeywordClassifier
    from backend.classifier.para_agent import run_para_agent
    from backend.classifier.snapshot_manager import SnapshotManager
except ImportError:
    import sys
    from pathlib import Path

    PROJECT_ROOT = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(PROJECT_ROOT))
    from backend.classifier.conflict_resolver import (
        ClassificationResult,
        ConflictResolver,
    )
    from backend.classifier.keyword import KeywordClassifier
    from backend.classifier.para_agent import run_para_agent
    from backend.classifier.snapshot_manager import SnapshotManager

    logger.warning("Import fallback used")

_RESOLVE_BATCH_UNAVAILABLE = False
try:
    from backend.api.endpoints.conflict_resolver_agent import resolve_conflicts_sync
except ImportError:
    _RESOLVE_BATCH_UNAVAILABLE = True
    logger.warning(
        "[ConflictService] resolve_conflicts_sync 로드 실패 — 배치 해결 기능 비활성화"
    )


class ConflictService:
    """
    통합 분류 서비스
    - PARA + Keyword + Conflict Resolution
    - Snapshot 관리 (Deep Copy)
    - 매번 새로운 분류 결과 생성하기
    """

    def __init__(self):
        """초기화"""
        # self.snapshots = {}
        # self.keyword_classifier = KeywordClassifier()
        self.snapshot_manager = SnapshotManager()
        self.keyword_classifier = KeywordClassifier()
        logger.info("✅ ConflictService 초기화 완료")

    async def classify_text(
        self,
        text: str,
        para_result: Optional[Dict[str, Any]] = None,
        keyword_result: Optional[Dict[str, Any]] = None,
        user_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        텍스트를 PARA + Keyword + Conflict로 분류

        - 매번 새로운 분류 결과 생성

        Args:
            text: 분류할 텍스트
            user_context: 사용자 컨텍스트 (선택)

        Returns:
            통합 분류 결과
        """
        # snapshot_id = f"snap_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

        # if user_context is None:
        #    user_context = {}

        try:
            logger.info("📝 통합 분류 시작: %s...", text[:50])

            # 1. PARA 분류 (이미 있으면 재사용)
            if para_result is None:
                logger.info("1. PARA 분류 실행...")
                para_result = await run_para_agent(text)

            para_result = para_result or {}
            logger.info("  ✅ PARA: %s", para_result.get("category"))

            # 2. Keyword 분류
            if keyword_result is None:
                logger.info("2. Keyword 분류 실행...")
                keyword_result = await self.keyword_classifier.classify(
                    text, user_context
                )

            keyword_result = keyword_result or {}
            logger.info("   ✅ 키워드: %s", keyword_result.get("tags", []))

            # 3. Conflict Resolution
            logger.info("3. Conflict Resolution 실행...")

            conflict_result = await self._resolve_conflict_async(
                para_result=para_result, keyword_result=keyword_result, text=text
            )

            # 4. Snapshot 저장
            logger.info("4. Snapshot 저장...")
            snapshot = self.snapshot_manager.save_snapshot(
                text=text,
                para_result=para_result,
                keyword_result=keyword_result,
                conflict_result=conflict_result,
            )

            # 5. 최종 결과
            result = {
                "snapshot_id": snapshot.id,
                "timestamp": snapshot.timestamp.isoformat(),
                "text": text[:100],
                "para_result": para_result,
                "keyword_result": keyword_result,
                "conflict_result": conflict_result,
                "metadata": snapshot.metadata,
                "status": "success",
            }

            logger.info("✅ 통합 분류 완료! Snapshot: %s", snapshot.id)
            return result

        except (OSError, ValueError, TypeError, RuntimeError) as e:
            meta_info = build_meta(
                snapshot_id=f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            log_agent_error(
                logger,
                "분류 오류 발생",
                e,
                meta_info,
                include_traceback=True,
            )

            return {
                "snapshot_id": meta_info["snapshot_id"],
                "timestamp": datetime.now().isoformat(),
                "text": text[:100],
                "error": "Classification failed due to internal error",
                "status": "error",
            }

    async def _resolve_conflict_async(
        self, para_result: Dict[str, Any], keyword_result: Dict[str, Any], text: str
    ) -> Dict[str, Any]:
        """
        충돌 해결 (ConflictResolver 사용)
        """

        try:
            # ClassificationResult 객체 생성
            para_obj = ClassificationResult(
                category=para_result.get("category", "Projects"),
                confidence=para_result.get("confidence", 0.8),
                source="para",
                reasoning=para_result.get("reasoning", ""),
                tags=None,
            )

            # Keyword 결과에서 category 우선 사용, 없으면 tags[0] 사용
            kw_category = keyword_result.get("category")
            if not kw_category and keyword_result.get("tags"):
                kw_category = keyword_result.get("tags")[0]

            keyword_obj = ClassificationResult(
                category=kw_category or "기타",
                confidence=keyword_result.get("confidence", 0.8),
                source="keyword",
                reasoning=keyword_result.get("reasoning", ""),
                tags=keyword_result.get("tags", ["기타"]),
            )

            # ConflictResolver로 해결
            resolver = ConflictResolver()

            # resolve_async가 있으면 사용, 없으면 sync 버전을 async로 실행
            if hasattr(resolver, "resolve_async"):
                conflict_result = await resolver.resolve_async(para_obj, keyword_obj)
            else:
                conflict_result = await asyncio.to_thread(
                    resolver.resolve, para_obj, keyword_obj
                )

            return conflict_result

        except (OSError, ValueError, TypeError, RuntimeError) as e:
            meta_info = build_meta()
            log_agent_error(
                logger,
                "충돌 해결 실패",
                e,
                meta_info,
                include_traceback=True,
            )
            # Fallback
            return {
                "final_category": para_result.get("category", "Projects"),
                "keyword_tags": keyword_result.get("tags", ["기타"]),
                "confidence": para_result.get("confidence", 0.8),
                "conflict_detected": False,
                "resolution_method": "simple_merge",
                "requires_review": False,
                "reason": "Fallback 해결",
            }

    # 스냅샷 관련 메서드
    def get_snapshots(self) -> list:
        """모든 스냅샷 조회"""
        return self.snapshot_manager.get_snapshots()

    def get_snapshot(self, snapshot_id: str) -> dict:
        """특정 스냅샷 조회"""
        return self.snapshot_manager.get_snapshot_by_id(snapshot_id)

    def compare_snapshots(self, id1: str, id2: str) -> dict:
        """2개 스냅샷 비교"""
        return self.snapshot_manager.compare_snapshots(id1, id2)

    def clear_snapshots(self):
        """모든 스냅샷 삭제"""
        self.snapshot_manager.clear_snapshots()
        logger.info("✅ 모든 스냅샷 삭제 완료")

    async def resolve_batch(self, conflicts: list) -> dict:
        """충돌 레코드 일괄 해결.

        이미 구현된 resolve_conflicts_sync 로직을 비동기 컵어로 호출합니다.
        해당 소스를 로드할 수 없는 경우에는 안전한 fallback 응답을 반환합니다.
        """
        total = len(conflicts)
        if not conflicts:
            return {
                "total_conflicts": 0,
                "detected_conflicts": [],
                "resolutions": [],
                "auto_resolved_count": 0,
                "manual_review_needed": 0,
                "resolution_rate": 0.0,
                "status": "completed",
                "summary": "충돌 없음",
            }

        if _RESOLVE_BATCH_UNAVAILABLE:
            logger.warning(
                "[ConflictService] resolve_conflicts_sync 미사용 가능 — 수동 검토 모드로 fallback"
            )
            return {
                "total_conflicts": total,
                "detected_conflicts": conflicts,
                "resolutions": [],
                "auto_resolved_count": 0,
                "manual_review_needed": total,
                "resolution_rate": 0.0,
                "status": "pending_review",
                "summary": f"{total}개 충돌 — 자동 해결 기능 시작 전 수동 검토 필요",
            }

        try:
            report = await asyncio.to_thread(resolve_conflicts_sync, conflicts)
            return {
                "total_conflicts": report.total_conflicts,
                "detected_conflicts": report.detected_conflicts,
                "resolutions": report.resolutions,
                "auto_resolved_count": report.auto_resolved_count,
                "manual_review_needed": report.manual_review_needed,
                "resolution_rate": report.resolution_rate,
                "status": report.status,
                "summary": report.summary,
            }
        except Exception as e:
            meta_info = build_meta()
            log_agent_error(
                logger,
                "[ConflictService] resolve_batch 실패 — fallback 반환",
                e,
                meta_info,
                include_traceback=True,
            )
            return {
                "total_conflicts": total,
                "detected_conflicts": conflicts,
                "resolutions": [],
                "auto_resolved_count": 0,
                "manual_review_needed": total,
                "resolution_rate": 0.0,
                "status": "error",
                "summary": f"{total}개 충돌 — 해결 중 오류 발생, 수동 검토 필요",
            }


# ✅ 싱글톤 인스턴스
conflict_service = ConflictService()
