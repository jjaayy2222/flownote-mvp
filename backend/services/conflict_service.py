# backend/services/conflict_service.py

"""
통합 분류 서비스: PARA + Keyword + Conflict Resolution
"""

import asyncio
from datetime import datetime
import uuid

from backend.classifier.para_agent import run_para_agent_sync  # ✅ 변경!

class ConflictService:
    def __init__(self):
        self.snapshots = {}
    
    def classify_text(self, text: str):
        """텍스트를 PARA + Keyword + Conflict로 분류 (동기)"""
        snapshot_id = f"snap_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        try:
            # ✅ CLI용 동기 함수 사용!
            para_result = run_para_agent_sync(text)
            
            # 임시로 간단한 결과 반환
            result = {
                "snapshot_id": snapshot_id,
                "para_result": para_result,
                "keyword_result": {"keywords": []},
                "conflict_result": {"is_conflict": False},
                "metadata": {"confidence": 0.8}
            }
            
            self.snapshots[snapshot_id] = result
            return result
            
        except Exception as e:
            print(f"❌ 분류 오류: {str(e)}")
            raise
    
    def get_snapshots(self):
        """저장된 스냅샷 조회"""
        return list(self.snapshots.values())

# ✅ 싱글톤 인스턴스
conflict_service = ConflictService()
