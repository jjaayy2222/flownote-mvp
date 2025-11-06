# backend/data_manager.py

import csv
import json
import os
from datetime import datetime
from pathlib import Path

class DataManager:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.users_file = self.data_dir / "users" / "users_profiles.csv"
        self.context_file = self.data_dir / "context" / "user_context_mapping.json"
        self.log_file = self.data_dir / "classifications" / "classification_log.csv"
        
        # 디렉토리 자동 생성
        for directory in [self.data_dir / "users", 
                        self.data_dir / "context",
                        self.data_dir / "classifications"]:
            directory.mkdir(parents=True, exist_ok=True)
    
    # ✅ 사용자 프로필 저장
    def save_user_profile(self, user_id: str, occupation: str, 
                        areas: list, interests: list) -> bool:
        """사용자 정보를 CSV에 저장"""
        try:
            with open(self.users_file, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    user_id,
                    occupation,
                    "|".join(areas),
                    "|".join(interests),
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                ])
            return True
        except Exception as e:
            print(f"Error saving profile: {e}")
            return False
    
    # ✅ 컨텍스트 맵핑 저장
    def save_context_mapping(self, user_id: str, context: dict) -> bool:
        """사용자의 P/A/R 의미 저장"""
        try:
            with open(self.context_file, "r+", encoding="utf-8") as f:
                data = json.load(f)
                data[user_id] = context
                f.seek(0)
                f.truncate()
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Error saving context: {e}")
            return False
    
    # ✅ 분류 로그 저장
    def log_classification(self, user_id: str, file_name: str,
                        ai_pred: str, user_sel: str, confidence: float) -> bool:
        """분류 결과 기록"""
        try:
            with open(self.log_file, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                status = "일치" if ai_pred == user_sel else "수정됨"
                writer.writerow([
                    datetime.now().isoformat(),
                    user_id,
                    file_name[:50],
                    ai_pred,
                    user_sel,
                    round(confidence, 2),
                    status
                ])
            return True
        except Exception as e:
            print(f"Error logging classification: {e}")
            return False
    
    # ✅ 사용자 정보 조회
    def get_user_profile(self, user_id: str) -> dict:
        """CSV에서 사용자 정보 읽기"""
        try:
            import pandas as pd
            df = pd.read_csv(self.users_file)
            user = df[df["user_id"] == user_id].iloc[0]
            return {
                "user_id": user_id,
                "occupation": user["occupation"],
                "areas": user["areas"].split("|"),
                "interests": user["interests"].split("|")
            }
        except Exception as e:
            print(f"Error getting profile: {e}")
            return None
    
    # ✅ 컨텍스트 맵핑 조회
    def get_context_mapping(self, user_id: str) -> dict:
        """JSON에서 컨텍스트 읽기"""
        try:
            with open(self.context_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get(user_id, {})
        except Exception as e:
            print(f"Error getting context: {e}")
            return {}
