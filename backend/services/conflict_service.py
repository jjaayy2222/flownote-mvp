# backend/services/conflict_service.py

"""
통합 분류 서비스: PARA + Keyword + Conflict Resolution

- Snapshot 기능 제거
- 매번 새로운 분류 결과 생성하기
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import uuid


logger = logging.getLogger(__name__)

# 필요한 분류기 import
try:
    from backend.classifier.para_agent import run_para_agent_sync
    from backend.classifier.keyword_classifier import KeywordClassifier
    from backend.classifier.conflict_resolver import ClassificationResult, ConflictResolver
    from backend.classifier.snapshot_manager import SnapshotManager
except ImportError:
    import sys
    from pathlib import Path
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(PROJECT_ROOT))
    from backend.classifier.para_agent import run_para_agent_sync
    from backend.classifier.keyword_classifier import KeywordClassifier
    from backend.classifier.conflict_resolver import ClassificationResult, ConflictResolver
    from backend.classifier.snapshot_manager import SnapshotManager
    logger.warning(f"Import fallback used: {e}")



class ConflictService:
    """
    통합 분류 서비스
    - PARA + Keyword + Conflict Resolution
    - Snapshot 관리 (Deep Copy)
    - 매번 새로운 분류 결과 생성하기
    """
    def __init__(self):
        """초기화"""
        #self.snapshots = {}
        self.keyword_classifier = KeywordClassifier()
        self.snapshot_manager = SnapshotManager()
        logger.info("✅ ConflictService 초기화 완료")
    
    def classify_text(
        self, 
        text: str,
        user_context: Optional[Dict[str, Any]] = None
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
        snapshot_id = f"snap_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        try:
            logger.info(f"📝 통합 분류 시작: {text[:50]}...")
            
            # 1. PARA 분류
            logger.info("1. PARA 분류 실행...")
            para_result = run_para_agent_sync(text)
            logger.info(f"  ✅ PARA: {para_result.get('category')}")
            
            # 2. Keyword 분류 (매번 새로운 키워드!)
            logger.info("2. Keyword 분류 실행...")
            keyword_result = self.keyword_classifier.classify(text, user_context)
            logger.info(f"  ✅ 새 키워드: {keyword_result.get('tags', [])}")
            
            # 3. Conflict Resolution (매번 새로운 통합!)
            logger.info("3. Conflict Resolution 실행...")
            conflict_result = self._simple_resolve_conflict(
                para_result=para_result,
                keyword_result=keyword_result,
                text=text
            )
            
            # 4. Snapshot 저장 (Deep Copy로 독립성 보장!)
            logger.info("4. Snapshot 저장...")
            
            snapshot = self.snapshot_manager.save_snapshot(
                text=text,
                para_result=para_result,
                keyword_result=keyword_result,
                conflict_result=conflict_result
            )
            
            # 5. 최종 결과
            result = {
                'snapshot_id': snapshot.id,
                'timestamp': snapshot.timestamp.isoformat(),
                'text': text[:100],
                'para_result': para_result,
                'keyword_result': keyword_result,
                'conflict_result': conflict_result,
                'metadata': snapshot.metadata,
                'status': 'success'
            }
            
            logger.info(f"✅ 통합 분류 완료! Snapshot: {snapshot.id}")
            return result
            
        except Exception as e:
            logger.error(f"❌ 분류 오류: {e}", exc_info=True)
            
            # 에러 결과도 Snapshot으로 저장
            error_result = {
                'snapshot_id': snapshot_id,
                'timestamp': datetime.now().isoformat(),
                'text': text[:100],
                'error': str(e),
                'status': 'error'
            }
            
            return error_result

    def _simple_resolve_conflict(
        self,
        para_result: Dict[str, Any],
        keyword_result: Dict[str, Any],
        text: str
    ) -> Dict[str, Any]:
        """
        간단한 충돌 해결
        
        ✅ ConflictResolver 없이도 동작!
        """
        # PARA 결과 우선
        final_category = para_result.get('category', 'Projects')
        
        # 키워드 추가
        final_keywords = keyword_result.get('tags', [])
        
        # 신뢰도 계산
        para_confidence = para_result.get('confidence', 0.8)
        keyword_confidence = keyword_result.get('confidence', 0.8)
        final_confidence = (para_confidence + keyword_confidence) / 2
        
        return {
            'final_category': final_category,
            'final_keywords': final_keywords,
            'confidence_score': final_confidence,
            'is_conflict': False,
            'resolution_method': 'simple_merge'
        }


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


# ✅ 싱글톤 인스턴스
conflict_service = ConflictService()
