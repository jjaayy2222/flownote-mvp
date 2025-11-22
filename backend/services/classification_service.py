"""
분류 비즈니스 로직 서비스 (Skeleton)
- PARA Agent + Keyword Classifier + Conflict Resolution 오케스트레이션
- 로깅 및 데이터 저장

이 파일은 Phase 4 Step 2에서 뼈대만 생성되었습니다.
실제 로직은 Step 3에서 구현됩니다.
"""

import logging
from typing import Dict, Any, List, Optional

# 모델 및 의존성 임포트
from backend.models import ClassifyResponse
from backend.services.conflict_service import ConflictService
from backend.data_manager import DataManager

# 추후 Step 3에서 실제 로직 구현 시 필요한 임포트들
# from backend.classifier.para_agent import run_para_agent
# from backend.classifier.keyword_classifier import KeywordClassifier

logger = logging.getLogger(__name__)


class ClassificationService:
    """
    분류 오케스트레이션 서비스

    책임:
    1. 사용자 컨텍스트 구성
    2. PARA 분류 실행
    3. 키워드 추출 실행
    4. 충돌 해결 (Conflict Service 위임)
    5. 결과 저장 및 로깅
    """

    def __init__(self):
        # 의존성 주입 (또는 내부 생성)
        self.conflict_service = ConflictService()
        self.data_manager = DataManager()
        logger.info("✅ ClassificationService initialized")

    async def classify(
        self,
        text: str,
        user_id: str = None,
        file_id: str = None,
        occupation: str = None,
        areas: list = None,
        interests: list = None,
    ) -> ClassifyResponse:
        """
        통합 분류 메서드 (Main Entry Point)

        Args:
            text: 분류할 텍스트 본문
            user_id: 사용자 ID
            file_id: 파일명 또는 ID
            occupation: 직업
            areas: 관심 영역 리스트
            interests: 관심사 리스트

        Returns:
            ClassifyResponse: 최종 분류 결과 모델
        """
        try:
            logger.info(f"🔵 분류 시작: user_id={user_id}, text_len={len(text)}")

            # Step 1: 사용자 컨텍스트 구성
            user_context = self._build_user_context(
                user_id, occupation, areas, interests
            )

            # Step 2: PARA 분류
            para_result = await self._run_para_classification(text, user_context)

            # Step 3: 키워드 추출
            keyword_result = await self._extract_keywords(text, user_context)

            # Step 4: 충돌 해결
            conflict_result = await self._resolve_conflicts(
                para_result, keyword_result, text, user_context
            )

            # Step 5: 최종 카테고리 결정
            final_category = (
                conflict_result.get("final_category")
                or para_result.get("category")
                or "Resources"
            )

            # Step 6: 결과 저장 (CSV + JSON) - Step 4에서 상세 구현
            # 현재는 기본 정보만 넘김
            log_info = self._save_results(
                user_id=user_id or "anonymous",
                file_id=file_id or "unknown",
                final_category=final_category,
                keyword_tags=keyword_result.get("tags", []),
                confidence=conflict_result.get("confidence", 0.0),
                snapshot_id=para_result.get("snapshot_id", ""),
            )

            # Step 7: 응답 생성
            response = ClassifyResponse(
                category=final_category,
                confidence=conflict_result.get("confidence", 0.0),
                snapshot_id=str(para_result.get("snapshot_id", "")),
                conflict_detected=conflict_result.get("conflict_detected", False),
                requires_review=conflict_result.get("requires_review", False),
                keyword_tags=keyword_result.get("tags", []),
                reasoning=conflict_result.get("reason", ""),
                user_context_matched=keyword_result.get("user_context_matched", False),
                user_areas=areas or [],
                user_context=user_context,
                context_injected=bool(areas),
                log_info=log_info,
            )

            logger.info(f"✅ 분류 완료: {final_category}")
            return response

        except Exception as e:
            logger.error(f"❌ 분류 실패: {e}", exc_info=True)
            raise

    # Private 메서드 구현
    def _build_user_context(self, user_id, occupation, areas, interests) -> dict:
        """사용자 컨텍스트 구성"""
        return {
            "user_id": user_id or "anonymous",
            "occupation": occupation or "일반 사용자",
            "areas": areas or [],
            "interests": interests or [],
            "context_keywords": {
                area: [area, f"{area} 관련", f"{area} 업무", f"{area} 프로젝트"]
                for area in (areas or [])
            },
        }

    async def _run_para_classification(self, text: str, metadata: dict) -> dict:
        """PARA 분류 실행"""
        from backend.classifier.para_agent import run_para_agent
        from datetime import datetime

        try:
            result = await run_para_agent(text=text, metadata=metadata)
            logger.info(f"✅ PARA: {result.get('category')}")
            return result
        except Exception as e:
            logger.error(f"❌ PARA 실패: {e}")
            return {
                "category": "Resources",
                "confidence": 0.0,
                "snapshot_id": f"snap_failed_{int(datetime.now().timestamp())}",
            }

    async def _extract_keywords(self, text: str, user_context: dict) -> dict:
        """키워드 추출"""
        from backend.classifier.keyword_classifier import KeywordClassifier

        classifier = KeywordClassifier()  # 매번 새 인스턴스 (상태 없음)
        result = await classifier.aclassify(text=text, user_context=user_context)

        # 태그 안전 처리
        tags = result.get("tags", [])
        if not isinstance(tags, list):
            tags = [str(tags)] if tags else ["기타"]
        elif not tags:
            tags = ["기타"]

        result["tags"] = tags
        logger.info(f"✅ Keywords: {tags[:5]}")
        return result

    async def _resolve_conflicts(
        self, para_result: dict, keyword_result: dict, text: str, user_context: dict
    ) -> dict:
        """충돌 해결"""
        result = await self.conflict_service.classify_text(
            para_result=para_result,
            keyword_result=keyword_result,
            text=text,
            user_context=user_context,
        )
        logger.info(f"✅ Conflict: {result.get('final_category')}")
        return result

    def _save_results(
        self,
        user_id: str,
        file_id: str,
        final_category: str,
        keyword_tags: list,
        confidence: float,
        snapshot_id: str,
    ) -> dict:
        """결과 저장 (CSV + JSON) (Private)"""
        # TODO: [Step 4] 상세 구현 예정
        # 현재는 로그만 남김
        return {
            "csv_saved": False,
            "json_saved": False,
            "message": "Step 4에서 구현 예정",
        }
