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
        self.log_dir = self.data_dir / "log"  # ← JSON 로그 디렉토리 추가
        
        # 디렉토리 생성
        self.users_dir.mkdir(parents=True, exist_ok=True)
        self.context_dir.mkdir(parents=True, exist_ok=True)
        self.classifications_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)  # ← 추가
        
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
    
    def save_user_profile(self, user_id: str, occupation: str, areas: List[str] = None, interests: List[str] = None):
        """
        사용자 프로필 저장 (신규)
        
        Args:
            user_id: 사용자 ID
            occupation: 직업
            areas: 관심 영역 리스트 (List[str])
            interests: 관심사 리스트 (List[str])
        """
        try:
            # 디버깅 코드
            print(f"🔵 [DATA_MANAGER] 저장 시도: user_id={user_id}, occupation={occupation}")
            print(f"🔵 [DATA_MANAGER] areas type: {type(areas)}, interests type: {type(interests)}")
            
            # None 처리
            if areas is None:
                areas = []
            if interests is None:
                interests = []
            
            # ✅ 타입 확인 및 변환
            if isinstance(areas, str):
                # 문자열인 경우 그대로 사용
                areas_str = areas
            elif isinstance(areas, list):
                # 리스트인 경우 join
                areas_str = ", ".join(areas)
            else:
                areas_str = ""
            
            if isinstance(interests, str):
                interests_str = interests
            elif isinstance(interests, list):
                interests_str = ", ".join(interests)
            else:
                interests_str = ""
            
            now = datetime.now().isoformat()
            
            with open(self.users_csv, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([user_id, occupation, areas_str, interests_str, now, now])
            
            print(f"✅ [DATA_MANAGER] 저장 완료!")
            return {"status": "success", "user_id": user_id}
        
        except Exception as e:
            print(f"❌ [DATA_MANAGER] 저장 실패: {str(e)}")
            import traceback
            traceback.print_exc()
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
    
    def update_user_areas(self, user_id: str, areas: List[str]):
        """
        사용자 영역 업데이트
        """
        try:
            # ✅ List[str] → str 변환
            if isinstance(areas, list):
                areas_str = ", ".join(areas)
            else:
                areas_str = areas  # 이미 문자열인 경우
            
            rows = []
            with open(self.users_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row["user_id"] == user_id:
                        row["areas"] = areas_str
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
        분류 결과 로그 저장 (CSV)
        """
        try:
            now = datetime.now().isoformat()
            status = "completed" if user_selected else "pending"
            
            with open(self.classifications_csv, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([now, user_id, file_name, ai_prediction, user_selected or "", confidence, status])
            
            print(f"✅ [CSV LOG] classification_log.csv 기록 완료: {file_name}")
            return {"status": "success"}
        except Exception as e:
            print(f"❌ [CSV LOG] 기록 실패: {e}")
            return {"status": "error", "message": str(e)}
    
    def save_classification_json(self, result: Dict, filename: str) -> str:
        """
        분류 결과 JSON 로그 저장 (data/log/)
        
        Args:
            result: 분류 결과 딕셔너리
            filename: 파일명
            
        Returns:
            저장된 JSON 파일 경로
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            json_filename = f"{timestamp}_{filename}.json"
            json_path = self.log_dir / json_filename
            
            # JSON 저장
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            print(f"✅ [JSON LOG] data/log/ 저장 완료: {json_filename}")
            return str(json_path)
            
        except Exception as e:
            print(f"❌ [JSON LOG] 저장 실패: {e}")
            return ""
    
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


def save_json_log(
    # self, 
    user_id: str,
    file_name: str,
    category: str,
    confidence: float,
    snapshot_id: str,
    conflict_detected: bool,
    requires_review: bool,
    keyword_tags: list,
    reasoning: str,
    user_context: str = "",
    user_profile: dict = None,
    context_injected: bool = False
):
    """
    data/log/ 폴더에 날짜+시간 기반 JSON 파일 저장
    """
    from datetime import datetime
    import json
    from pathlib import Path
    
    # 로그 디렉토리 생성
    log_dir = Path("data/log")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 타임스탬프 생성
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 파일명에서 확장자 제거
    base_filename = Path(file_name).stem
    
    # JSON 파일명
    json_filename = f"{timestamp}_{base_filename}.json"
    json_path = log_dir / json_filename
    
    # JSON 데이터 구성
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id,
        "file_name": file_name,
        "category": category,
        "confidence": confidence,
        "snapshot_id": str(snapshot_id),
        "conflict_detected": conflict_detected,
        "requires_review": requires_review,
        "keyword_tags": keyword_tags,
        "reasoning": reasoning,
        "user_context": user_context,
        "user_profile": user_profile or {},
        "context_injected": context_injected
    }
    
    # JSON 파일 저장
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ [JSON LOG] {json_filename} 저장 완료!")
    return str(json_path)

