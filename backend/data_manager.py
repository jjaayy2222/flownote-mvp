# backend/data_manager.py

"""
FlowNote MVP - Data Management Module (데이터 관리 모듈).

[KO] 사용자 프로필(CSV), 컨텍스트 맵핑(JSON), 분류 로그 등을 파일 입출력으로 관리합니다.
     데이터를 로컬 파일 시스템에 저장하고 조회하는 역할을 담당합니다.
[EN] Manages user profiles (CSV), context mapping (JSON), and classification logs via file I/O.
     Responsible for saving and retrieving data from the local file system.
"""

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class DataManager:
    """
    [KO] 데이터 저장 및 조회를 전담하는 매니저 클래스.
    [EN] Manager class dedicated to saving and retrieving data.
    """

    def __init__(self):
        """
        [KO] DataManager를 초기화하고 필요한 디렉토리(users, context, log 등)를 생성합니다.
        [EN] Initializes the DataManager and creates necessary directories (users, context, log, etc.).
        """
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
        """
        [KO] 초기 CSV 및 JSON 파일(헤더 포함)이 존재하지 않으면 생성합니다.
        [EN] Creates initial CSV and JSON files (including headers) if they do not exist.
        """
        # users_profiles.csv 헤더
        if not self.users_csv.exists():
            with open(self.users_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "user_id",
                        "occupation",
                        "areas",
                        "interests",
                        "created_at",
                        "updated_at",
                    ]
                )

        # user_context_mapping.json 초기화
        if not self.context_json.exists():
            with open(self.context_json, "w", encoding="utf-8") as f:
                json.dump({}, f)

        # classification_log.csv 헤더
        if not self.classifications_csv.exists():
            with open(self.classifications_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "timestamp",
                        "user_id",
                        "file_name",
                        "ai_prediction",
                        "user_selected",
                        "confidence",
                        "status",
                    ]
                )

    @staticmethod
    def _join_list(data) -> str:
        """
        [KO] 리스트 데이터를 쉼표(,)로 연결된 문자열로 변환합니다.
        [EN] Converts list data to a comma-separated string.
        """
        if isinstance(data, str):
            return data
        return ", ".join(data) if isinstance(data, list) else ""

    # =====================
    # 👤 사용자 프로필 관리
    # =====================

    def _write_profile_to_csv(
        self, user_id: str, occupation: str, areas_str: str, interests_str: str
    ):
        """[KO] 사용자 프로필을 CSV에 물리적으로 기록합니다."""
        now = datetime.now().isoformat()
        with open(self.users_csv, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([user_id, occupation, areas_str, interests_str, now, now])

    def save_user_profile(
        self,
        user_id: str,
        occupation: str,
        areas: Optional[List[str]] = None,
        interests: Optional[List[str]] = None,
    ):
        """
        [KO] 신규 사용자 프로필을 CSV 파일에 저장합니다.
        [EN] Saves a new user profile to the CSV file.

        Args:
            user_id (str): 사용자 ID / User ID
            occupation (str): 직업 / Occupation
            areas (List[str], optional): 관심 영역 리스트 / List of areas of interest
            interests (List[str], optional): 관심사 리스트 / List of specific interests
        """
        try:
            areas_str = self._join_list(areas)
            interests_str = self._join_list(interests)

            self._write_profile_to_csv(user_id, occupation, areas_str, interests_str)

            print("✅ [DATA_MANAGER] 저장 완료!")
            return {"status": "success", "user_id": user_id}

        except Exception as e:
            print(f"❌ [DATA_MANAGER] 저장 실패: {str(e)}")
            import traceback

            traceback.print_exc()
            return {"status": "error", "message": str(e)}

    def get_user_profile(self, user_id: str) -> Optional[Dict]:
        """
        [KO] CSV 파일에서 특정 사용자의 프로필 정보를 조회합니다.
        [EN] Retrieves a specific user's profile information from the CSV file.

        Args:
            user_id (str): 조회할 사용자 ID / User ID to look up
        Returns:
            Optional[Dict]: 사용자 프로필 딕셔너리 또는 None / User profile dictionary or None if not found
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
        [KO] 기존 사용자의 관심 영역(areas) 정보를 업데이트합니다.
        [EN] Updates the areas of interest for an existing user.

        Args:
            user_id (str): 사용자 ID / User ID
            areas (List[str]): 업데이트할 관심 영역 리스트 / Updated list of areas
        Returns:
            Dict: 업데이트 결과 상태 딕셔너리 / Dictionary containing the update status
        """
        try:
            # ✅ List[str] → str 변환
            areas_str = self._join_list(areas)

            rows = []
            with open(self.users_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row["user_id"] == user_id:
                        row["areas"] = areas_str
                        row["updated_at"] = datetime.now().isoformat()
                    rows.append(row)

            with open(self.users_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "user_id",
                        "occupation",
                        "areas",
                        "interests",
                        "created_at",
                        "updated_at",
                    ],
                )
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
        [KO] 사용자 맥락(Context) 데이터를 JSON 파일에 저장합니다.
        [EN] Saves user context data to the JSON file.

        Args:
            user_id (str): 사용자 ID / User ID
            areas (List[str]): 사용자 맥락(영역) 리스트 / List of user context areas
        Returns:
            Dict: 저장 결과 상태 딕셔너리 / Dictionary containing the save status
        """
        try:
            with open(self.context_json, "r", encoding="utf-8") as f:
                context_data = json.load(f)

            context_data[user_id] = {
                "areas": areas,
                "created_at": datetime.now().isoformat(),
            }

            with open(self.context_json, "w", encoding="utf-8") as f:
                json.dump(context_data, f, ensure_ascii=False, indent=2)

            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_user_context(self, user_id: str) -> Optional[Dict]:
        """
        [KO] JSON 파일에서 특정 사용자의 맥락(Context) 데이터를 조회합니다.
        [EN] Retrieves a specific user's context data from the JSON file.

        Args:
            user_id (str): 사용자 ID / User ID
        Returns:
            Optional[Dict]: 사용자 맥락 딕셔너리 또는 None / User context dictionary or None if not found
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
        [KO] 사용자 맥락에서 영역(areas) 목록만 추출하여 반환합니다.
        [EN] Extracts and returns only the areas list from the user's context.

        Args:
            user_id (str): 사용자 ID / User ID
        Returns:
            List[str]: 사용자 영역 리스트 / List of user areas
        """
        context = self.get_user_context(user_id)
        return context.get("areas", []) if context else []

    # =====================
    # 📊 분류 로그 관리
    # =====================

    def log_classification(
        self,
        user_id: str,
        file_name: str,
        ai_prediction: str,
        user_selected: Optional[str],
        confidence: float,
    ):
        """
        [KO] AI의 분류 결과 및 사용자 선택 결과를 CSV 파일에 로그로 남깁니다.
        [EN] Logs the AI classification and user selection results to the CSV file.

        Args:
            user_id (str): 사용자 ID / User ID
            file_name (str): 분류된 파일명 / Name of the classified file
            ai_prediction (str): AI가 예측한 분류 / AI predicted category
            user_selected (Optional[str]): 사용자가 최종 선택한 분류 / Final category selected by the user
            confidence (float): AI 예측 신뢰도 / AI prediction confidence score
        Returns:
            Dict: 저장 결과 상태 딕셔너리 / Dictionary containing the log status
        """
        try:
            now = datetime.now().isoformat()
            status = "completed" if user_selected else "pending"

            with open(self.classifications_csv, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        now,
                        user_id,
                        file_name,
                        ai_prediction,
                        user_selected or "",
                        confidence,
                        status,
                    ]
                )

            print(f"✅ [CSV LOG] classification_log.csv 기록 완료: {file_name}")
            return {"status": "success"}
        except Exception as e:
            print(f"❌ [CSV LOG] 기록 실패: {e}")
            return {"status": "error", "message": str(e)}

    def save_classification_json(self, result: Dict, filename: str) -> str:
        """
        [KO] 상세 분류 결과를 JSON 파일 형태로 지정된 로그 디렉토리에 저장합니다.
        [EN] Saves the detailed classification results as a JSON file in the log directory.

        Args:
            result (Dict): 분류 결과 딕셔너리 / Classification result dictionary
            filename (str): 원본 파일명 / Original file name
        Returns:
            str: 저장된 JSON 파일의 절대 경로 / Absolute path to the saved JSON file
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
        [KO] 특정 사용자의 과거 분류 히스토리를 CSV에서 읽어 반환합니다.
        [EN] Retrieves a specific user's classification history from the CSV file.

        Args:
            user_id (str): 사용자 ID / User ID
        Returns:
            List[Dict]: 분류 히스토리 리스트 / List of classification history records
        """
        try:
            with open(self.classifications_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                classifications = [
                    dict(row) for row in reader if row["user_id"] == user_id
                ]
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
    user_profile: Optional[dict] = None,
    context_injected: bool = False,
):
    """
    [KO] 글로벌 함수: data/log/ 디렉토리에 타임스탬프를 포함한 JSON 로그를 저장합니다.
    [EN] Global function: Saves a timestamped JSON log file in the data/log/ directory.

    Args:
        user_id (str): 사용자 ID / User ID
        file_name (str): 처리된 파일명 / Processed file name
        category (str): 결정된 카테고리 / Determined category
        confidence (float): 예측 신뢰도 / Prediction confidence
        snapshot_id (str): 스냅샷 ID / Snapshot ID
        conflict_detected (bool): 충돌 감지 여부 / Whether a conflict was detected
        requires_review (bool): 검토 필요 여부 / Whether review is required
        keyword_tags (list): 키워드 태그 리스트 / List of keyword tags
        reasoning (str): AI 추론 논리 / AI reasoning logic
        user_context (str, optional): 사용자 컨텍스트 요약 / User context summary
        user_profile (Optional[dict], optional): 사용자 프로필 데이터 / User profile data
        context_injected (bool, optional): 컨텍스트 주입 여부 / Whether context was injected
    Returns:
        str: 저장된 JSON 로그 파일 경로 / Path to the saved JSON log file
    """
    import json
    from datetime import datetime
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
        "snapshot_id": snapshot_id,
        "conflict_detected": conflict_detected,
        "requires_review": requires_review,
        "keyword_tags": keyword_tags,
        "reasoning": reasoning,
        "user_context": user_context,
        "user_profile": user_profile or {},
        "context_injected": context_injected,
    }

    # JSON 파일 저장
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)

    print(f"✅ [JSON LOG] {json_filename} 저장 완료!")
    return str(json_path)
