# backend/classifier/snapshot_manager.py

"""
Snapshot 관리 클래스
    - 분류 결과 저장 구조 정리
    - 비교 로직은 나중에 구현 예정
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any
import json
import copy

@dataclass
class Snapshot:
    """분류 결과 스냅샷"""
    id: str
    timestamp: datetime
    text: str
    para_result: dict
    keyword_result: dict
    conflict_result: dict
    metadata: dict
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "text": self.text,
            "para_result": self.para_result,
            "keyword_result": self.keyword_result,
            "conflict_result": self.conflict_result,
            "metadata": self.metadata,
        }

class SnapshotManager:
    """스냅샷 저장 및 관리"""
    
    def __init__(self):
        self.snapshots: List[Snapshot] = []
    
    def save_snapshot(self, text: str, para_result: dict, 
                    keyword_result: dict, conflict_result: dict) -> Snapshot:
        """
        분류 결과 저장
        
        - Deep Copy로 데이터 독립성 보장하기
        """
        snapshot = Snapshot(
            id=f"snap_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",  # ← 밀리초 추가!
            timestamp=datetime.now(),
            text=text,
            # Deep Copy로 독립적인 복사본 저장
            para_result=copy.deepcopy(para_result),
            keyword_result=copy.deepcopy(keyword_result),
            conflict_result=copy.deepcopy(conflict_result),
            metadata={
                "confidence": conflict_result.get("confidence_score", 0),
                "is_conflict": conflict_result.get("is_conflict", False),
                "final_category": conflict_result.get("final_category"),
            }
        )
        self.snapshots.append(snapshot)
        return snapshot
    
    def get_snapshots(self) -> List[dict]:
        """모든 스냅샷 반환"""
        return [s.to_dict() for s in self.snapshots]

    def get_snapshot_by_id(self, snapshot_id: str) -> dict:
        """ID로 스냅샷 조회"""
        for snapshot in self.snapshots:
            if snapshot.id == snapshot_id:
                return snapshot.to_dict()
        return {"error": "Snapshot not found"}

    def compare_snapshots(self, id1: str, id2: str) -> dict:
        """2개 스냅샷 비교"""
        snap1 = next((s for s in self.snapshots if s.id == id1), None)
        snap2 = next((s for s in self.snapshots if s.id == id2), None)
        
        if not snap1 or not snap2:
            return {"error": "Snapshot not found"}
        
        return {
            "snap1_id": id1,
            "snap2_id": id2,
            "same_text": snap1.text == snap2.text,
            "para_diff": snap1.para_result != snap2.para_result,
            "keyword_diff": snap1.keyword_result != snap2.keyword_result,
            "conflict_diff": snap1.conflict_result != snap2.conflict_result,
        }
    
    def clear_snapshots(self):
        """모든 스냅샷 삭제"""
        self.snapshots.clear()
