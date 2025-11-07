# backend/data_manager.py

"""
💾 데이터 관리 모듈
CSV/JSON 파일 I/O + 사용자 데이터 관리
"""

import os
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

class DataManager:
    """데이터 저장/조회 담당"""
    
    def __init__(self):
        """초기화 및 디렉토리 생성"""
        self.data_dir = Path("data")
        self.users_dir = self.data_dir / "users"
        self.context_dir = self.data_dir / "context"
        self.classifications_dir = self.data_dir / "classifications"
        
        # 디렉토리 생성
        self.users_dir.mkdir(parents=True, exist_ok=True)
        self.context_dir.mkdir(parents=True, exist_ok=True)
        self.classifications_dir.mkdir(parents=True, exist_ok=True)
        
        # CSV 파일 경로
        self.users_csv = self.users_dir / "users_profiles.csv"
        self.context_json = self.context_dir / "user_context_mapping.json"
        self.classifications_csv = self.classifications_dir / "classification_log.csv"
        
        # 초기 파일 생성
        self._initialize_files()
    
    def _initialize_files(self):
        """필요한 파일 초기화"""
        # users_profiles.csv 헤더
        if not self.users_csv.exists():
            with open(self.users_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["user_id", "occupation", "areas", "interests", "created_at", "updated_at"])
        
        # user_context_mapping.json 초기화
        if not self.context_json.exists():
            with open(self.context_json, "w", encoding="utf-8") as f:
                json.dump({}, f)
        
        # classification_log.csv 헤더
        if not self.classifications_csv.exists():
            with open(self.classifications_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "user_id", "file_name", "ai_prediction", "user_selected", "confidence", "status"])
    
    # =====================
    # 👤 사용자 프로필 관리
    # =====================
    
    def save_user_profile(self, user_id: str, occupation: str, areas: str = "", interests: str = ""):
        """
        사용자 프로필 저장 (신규)
        """
        try:
            now = datetime.now().isoformat()
            
            with open(self.users_csv, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([user_id, occupation, areas, interests, now, now])
            
            return {"status": "success", "user_id": user_id}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def get_user_profile(self, user_id: str) -> Optional[Dict]:
        """
        사용자 프로필 조회
        """
        try:
            with open(self.users_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row["user_id"] == user_id:
                        return dict(row)
            return None
        except Exception as e:
            print(f"프로필 조회 실패: {str(e)}")
            return None
    
    def update_user_areas(self, user_id: str, areas: str):
        """
        사용자 영역 업데이트
        """
        try:
            rows = []
            with open(self.users_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row["user_id"] == user_id:
                        row["areas"] = areas
                        row["updated_at"] = datetime.now().isoformat()
                    rows.append(row)
            
            with open(self.users_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["user_id", "occupation", "areas", "interests", "created_at", "updated_at"])
                writer.writeheader()
                writer.writerows(rows)
            
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    # =====================
    # 🎯 사용자 맥락 관리
    # =====================
    
    def save_user_context(self, user_id: str, areas: List[str]):
        """
        사용자 맥락 저장 (JSON)
        """
        try:
            with open(self.context_json, "r", encoding="utf-8") as f:
                context_data = json.load(f)
            
            context_data[user_id] = {
                "areas": areas,
                "created_at": datetime.now().isoformat()
            }
            
            with open(self.context_json, "w", encoding="utf-8") as f:
                json.dump(context_data, f, ensure_ascii=False, indent=2)
            
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def get_user_context(self, user_id: str) -> Optional[Dict]:
        """
        사용자 맥락 조회
        """
        try:
            with open(self.context_json, "r", encoding="utf-8") as f:
                context_data = json.load(f)
            
            return context_data.get(user_id, None)
        except Exception as e:
            print(f"컨텍스트 조회 실패: {str(e)}")
            return None
    
    def get_user_areas(self, user_id: str) -> List[str]:
        """
        사용자 영역 목록 반환
        """
        context = self.get_user_context(user_id)
        if context:
            return context.get("areas", [])
        return []
    
    # =====================
    # 📊 분류 로그 관리
    # =====================
    
    def log_classification(self, user_id: str, file_name: str, ai_prediction: str, 
                        user_selected: Optional[str], confidence: float):
        """
        분류 결과 로그 저장
        """
        try:
            now = datetime.now().isoformat()
            status = "completed" if user_selected else "pending"
            
            with open(self.classifications_csv, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([now, user_id, file_name, ai_prediction, user_selected or "", confidence, status])
            
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def get_user_classifications(self, user_id: str) -> List[Dict]:
        """
        사용자의 분류 히스토리 조회
        """
        try:
            classifications = []
            with open(self.classifications_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row["user_id"] == user_id:
                        classifications.append(dict(row))
            return classifications
        except Exception as e:
            print(f"분류 히스토리 조회 실패: {str(e)}")
            return []




