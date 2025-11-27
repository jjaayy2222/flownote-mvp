"""
온보딩 비즈니스 로직 서비스
- 사용자 생성
- AI 기반 영역 추천
- 컨텍스트 저장
"""

import uuid
import logging
from typing import List, Dict, Any
from backend.data_manager import DataManager
from backend.services.gpt_helper import get_gpt_helper

logger = logging.getLogger(__name__)


class OnboardingService:
    """온보딩 플로우 관리 서비스"""
    
    def __init__(self):
        self.data_manager = DataManager()
        self.gpt_helper = get_gpt_helper()
    
    def create_user(self, occupation: str, name: str = None) -> Dict[str, Any]:
        """Step 1: 사용자 생성
        
        Args:
            occupation: 직업
            name: 이름 (선택)
            
        Returns:
            {
                "user_id": "user_abc123",
                "occupation": "개발자",
                "status": "created"
            }
        """
        try:
            user_id = f"user_{str(uuid.uuid4())[:8]}"
            
            # 데이터 저장
            self.data_manager.save_user_profile(
                user_id=user_id,
                occupation=occupation,
                areas="",  # 아직 선택 안 함
                interests=""
            )
            
            logger.info(f"✅ 사용자 생성: {user_id} ({occupation})")
            
            return {
                "status": "success",
                "user_id": user_id,
                "occupation": occupation,
                "message": "Step 1 완료! 이제 영역을 추천받으세요"
            }
            
        except Exception as e:
            logger.error(f"❌ 사용자 생성 실패: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def suggest_areas(self, user_id: str, occupation: str) -> Dict[str, Any]:
        """Step 2: GPT-4o로 영역 추천
        
        Args:
            user_id: 사용자 ID
            occupation: 직업
            
        Returns:
            {
                "suggested_areas": ["영역1", "영역2", ...],
                "status": "success"
            }
        """
        try:
            # GPT-4o 호출
            result = self.gpt_helper.suggest_areas(occupation)
            
            if result.get("status") == "error":
                raise Exception(result.get("message"))
            
            suggested_areas = result.get("areas", [])
            
            logger.info(f"✅ 영역 추천 완료: {len(suggested_areas)}개")
            
            return {
                "status": "success",
                "user_id": user_id,
                "occupation": occupation,
                "suggested_areas": suggested_areas
            }
            
        except Exception as e:
            logger.error(f"❌ 영역 추천 실패: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def save_user_context(self, user_id: str, selected_areas: List[str]) -> Dict[str, Any]:
        """Step 3: 사용자가 선택한 영역 저장
        
        Args:
            user_id: 사용자 ID
            selected_areas: 선택한 영역 리스트
            
        Returns:
            {"status": "success", "message": "..."}
        """
        try:
            # 1. CSV 업데이트 (areas 채우기)
            self.data_manager.update_user_areas(
                user_id=user_id,
                areas=selected_areas  # DataManager가 알아서 문자열로 변환
            )
            
            # 2. JSON 컨텍스트 저장
            result = self.data_manager.save_user_context(
                user_id=user_id,
                areas=selected_areas
            )
            
            if result.get("status") == "error":
                raise Exception(result.get("message"))
            
            logger.info(f"✅ 컨텍스트 저장 완료: {user_id}")
            
            return {
                "status": "success",
                "user_id": user_id,
                "selected_areas": selected_areas,
                "message": "온보딩이 완료되었습니다"
            }
            
        except Exception as e:
            logger.error(f"❌ 컨텍스트 저장 실패: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def get_user_status(self, user_id: str) -> Dict[str, Any]:
        """사용자 온보딩 상태 조회
        
        Args:
            user_id: 사용자 ID
            
        Returns:
            {
                "is_completed": True/False,
                "occupation": "...",
                "areas": [...]
            }
        """
        try:
            user_data = self.data_manager.get_user_profile(user_id)
            
            if not user_data:
                return {
                    "status": "error",
                    "message": "사용자를 찾을 수 없습니다"
                }
            
            areas_str = user_data.get("areas", "")
            areas_list = [a.strip() for a in areas_str.split(",")] if areas_str else []
            
            is_completed = bool(areas_list)
            
            return {
                "status": "success",
                "user_id": user_id,
                "occupation": user_data.get("occupation"),
                "areas": areas_list,
                "is_completed": is_completed
            }
            
        except Exception as e:
            logger.error(f"❌ 상태 조회 실패: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
