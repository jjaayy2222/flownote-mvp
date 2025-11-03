# backend/database/metadata_schema.py

from backend.database.connection import DatabaseConnection
from typing import Dict, List
from datetime import datetime


class ClassificationMetadataExtender:
    """기존 DB 스키마 확장"""
    
    def __init__(self, db: DatabaseConnection = None):
        self.db = db or DatabaseConnection()
        self._extend_schema()
    
    def _extend_schema(self):
        """스키마 확장 (안전하게!)"""
        try:
            # 컬럼 존재 여부 확인
            cursor = self.db.cursor.execute("PRAGMA table_info(metadata)")
            existing_columns = [row[1] for row in cursor.fetchall()]
            
            # 1. conflict_flag 추가
            if "conflict_flag" not in existing_columns:
                self.db.cursor.execute("""
                    ALTER TABLE metadata 
                    ADD COLUMN conflict_flag BOOLEAN DEFAULT FALSE
                """)
                print("✅ conflict_flag 컬럼 추가 완료")
            
            # 2. resolution_method 추가
            if "resolution_method" not in existing_columns:
                self.db.cursor.execute("""
                    ALTER TABLE metadata 
                    ADD COLUMN resolution_method TEXT
                """)
                print("✅ resolution_method 컬럼 추가 완료")
            
            # 3. snapshot_id 추가
            if "snapshot_id" not in existing_columns:
                self.db.cursor.execute("""
                    ALTER TABLE metadata 
                    ADD COLUMN snapshot_id TEXT
                """)
                print("✅ snapshot_id 컬럼 추가 완료")
            
            self.db.conn.commit()
            
        except Exception as e:
            print(f"❌ 스키마 확장 실패: {e}")
    

    def save_classification_result(self, result: dict, filename: str = None) -> int:
        """
        para_agent.py의 최종 결과를 DB에 저장
        
        Args:
            result: run_para_agent_sync()의 반환값
            filename: 파일명 (없으면 text 기반 생성)
        """
        
        # 1. 파일 생성 또는 가져오기
        if filename is None:
            # text를 파일명으로 사용
            filename = f"{result.get('category', 'unknown')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        file_id = self._get_or_create_file(filename)
        
        # ✅ 2. snapshot_id 처리 (Snapshot 객체 → 문자열)
        snapshot_id = result.get("snapshot_id", "")
        
        # ✅ Snapshot 객체인 경우 .id 추출
        if hasattr(snapshot_id, 'id'):
            snapshot_id = snapshot_id.id
        elif not isinstance(snapshot_id, str):
            snapshot_id = str(snapshot_id)
        
        # ✅ 3. para_result에서 snapshot_id가 있는 경우도 체크
        if not snapshot_id and "para_result" in result:
            para_snapshot = result["para_result"].get("snapshot_id", "")
            if hasattr(para_snapshot, 'id'):
                snapshot_id = para_snapshot.id
            elif para_snapshot:
                snapshot_id = str(para_snapshot)
        
        # 4. metadata 테이블에 저장
        self.db.cursor.execute("""
            INSERT OR REPLACE INTO metadata 
            (file_id, para_category, keyword_tags, confidence_score, 
             manual_override, conflict_flag, resolution_method, snapshot_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            file_id,
            result.get("category"),
            ",".join(result.get("keyword_tags", [])),
            result.get("confidence", 0.0),
            False,
            result.get("conflict_detected", False),
            result.get("reasoning", "")[:200],          # ✅ 길이 제한 (200자)
            snapshot_id[:50]                            # ✅ snapshot_id도 길이 제한
        ))
        
        self.db.conn.commit()
        
        print(f"✅ 분류 결과 저장 완료: file_id={file_id}, snapshot_id={snapshot_id}")
        return file_id

    def _get_or_create_file(self, filename: str) -> int:
        """파일 ID 가져오거나 생성"""
        
        # 기존 파일 확인
        result = self.db.cursor.execute(
            "SELECT id FROM files WHERE filename = ?", (filename,)
        ).fetchone()
        
        if result:
            return result[0]
        
        # 새 파일 생성
        self.db.cursor.execute("""
            INSERT INTO files (filename, file_type, created_date, updated_date, path)
            VALUES (?, ?, ?, ?, ?)
        """, (filename, "text", datetime.now(), datetime.now(), f"data/{filename}"))
        
        self.db.conn.commit()
        
        return self.db.cursor.lastrowid
    
    def get_all_classifications(self) -> List[Dict]:
        """모든 분류 결과 조회"""
        
        result = self.db.cursor.execute("""
            SELECT 
                f.filename,
                m.para_category,
                m.keyword_tags,
                m.confidence_score,
                m.conflict_flag,
                m.resolution_method,
                m.snapshot_id
            FROM files f
            JOIN metadata m ON f.id = m.file_id
        """).fetchall()
        
        return [dict(row) for row in result]
