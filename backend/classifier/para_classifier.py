# backend/classifier/para_classifier.py 

"""
PARA 분류기 모듈
텍스트를 Projects, Areas, Resources, Archives로 자동 분류
"""

from typing import Dict, Tuple
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class PARAClassifier:
    """
    PARA 시스템 기반 자동 분류 클래스
    
    Projects: 명확한 기한과 목표가 있는 작업
    Areas: 지속적으로 관심있는 영역
    Resources: 참고용 자료/정보
    Archives: 완료되었거나 더 이상 사용하지 않는 것
    """
    
    CATEGORIES = {
        "Projects": {
            "icon": "📋",
            "color": "#3498db",         # 파란색
            "description": "명확한 기한과 목표가 있는 작업"
        },
        "Areas": {
            "icon": "🎯",
            "color": "#2ecc71",         # 초록색
            "description": "지속적으로 관심있는 영역"
        },
        "Resources": {
            "icon": "📚",
            "color": "#f39c12",         # 노란색
            "description": "참고용 자료 및 정보"
        },
        "Archives": {
            "icon": "📦",
            "color": "#95a5a6",         # 회색
            "description": "완료되었거나 미사용 항목"
        }
    }
    
    def __init__(self):
        """분류기 초기화"""
        self.categories = self.CATEGORIES
        self.classification_history = []
        logger.info("PARAClassifier initialized")
    
    def classify_text(
        self, 
        text: str,
        filename: str = "unknown"
    ) -> Dict:
        """
        텍스트를 PARA 카테고리로 분류 (기본 규칙 기반)
        
        Args:
            text (str): 분류할 텍스트
            filename (str): 파일명 (참고용)
        
        Returns:
            Dict: 분류 결과 + confidence score
        """
        if not text or not isinstance(text, str):
            logger.warning(f"Invalid text input for {filename}")
            return {
                "category": "Resources",
                "confidence": 0.0,
                "reason": "Invalid input"
            }
        
        # 텍스트 전처리
        text_lower = text.lower()
        
        # 점수 계산
        scores = self._calculate_scores(text_lower, filename)
        
        # 최고 점수 카테고리 선택
        best_category = max(scores.items(), key=lambda x: x[1])
        category_name = best_category[0]
        confidence = min(best_category[1] / 100, 1.0)  # 0~1 정규화
        
        result = {
            "category": category_name,
            "confidence": round(confidence, 2),
            "scores": scores,
            "timestamp": datetime.now().isoformat(),
            "filename": filename
        }
        
        # 히스토리 저장
        self._save_to_history(result)
        
        logger.info(
            f"Classified '{filename}' as '{category_name}' "
            f"(confidence: {confidence:.2%})"
        )
        
        return result
    
    def _calculate_scores(self, text: str, filename: str) -> Dict[str, float]:
        """
        키워드 기반 점수 계산 (프로토타입)
        나중에 LangChain으로 업그레이드!
        """
        scores = {
            "Projects": 0.0,
            "Areas": 0.0,
            "Resources": 0.0,
            "Archives": 0.0
        }
        
        # Projects 키워드 (기한, 목표, 진행)
        project_keywords = [
            "deadline", "due date", "goal", "target", "task", "sprint",
            "todo", "action", "plan", "schedule", "milestone", "progress",
            "진행중", "마감", "목표", "과제", "계획", "스프린트"
        ]
        
        # Areas 키워드 (관심, 학습, 관리)
        area_keywords = [
            "learning", "study", "skill", "development", "improvement",
            "habit", "routine", "interest", "passion", "expertise",
            "학습", "공부", "기술", "개선", "습관", "관심"
        ]
        
        # Resources 키워드 (참고, 정보, 자료)
        resource_keywords = [
            "reference", "resource", "guide", "tutorial", "documentation",
            "article", "blog", "template", "example", "tool",
            "참고", "자료", "가이드", "템플릿", "예제", "링크"
        ]
        
        # Archives 키워드 (완료, 미사용, 보관)
        archive_keywords = [
            "completed", "finished", "done", "old", "deprecated",
            "deprecated", "outdated", "archived", "inactive",
            "완료", "끝", "구식", "보관", "미사용"
        ]
        
        # 점수 계산
        scores["Projects"] += self._count_keywords(text, project_keywords) * 20
        scores["Areas"] += self._count_keywords(text, area_keywords) * 20
        scores["Resources"] += self._count_keywords(text, resource_keywords) * 20
        scores["Archives"] += self._count_keywords(text, archive_keywords) * 20
        
        # 파일명 기반 추가 점수
        filename_lower = filename.lower()
        if "archive" in filename_lower or "old" in filename_lower:
            scores["Archives"] += 30
        elif "resource" in filename_lower or "guide" in filename_lower:
            scores["Resources"] += 30
        elif "project" in filename_lower or "task" in filename_lower:
            scores["Projects"] += 30
        
        # 기본값 (어떤 카테고리도 점수가 0이면 Resources로)
        if sum(scores.values()) == 0:
            scores["Resources"] = 50
        
        return scores
    
    def _count_keywords(self, text: str, keywords: list) -> int:
        """텍스트에 포함된 키워드 개수 카운트"""
        count = 0
        for keyword in keywords:
            if keyword in text:
                count += text.count(keyword)
        return count
    
    def _save_to_history(self, result: Dict):
        """분류 결과를 히스토리에 저장"""
        self.classification_history.append(result)
        if len(self.classification_history) > 1000:
            # 최근 1000개만 유지
            self.classification_history = self.classification_history[-1000:]
    
    def get_category_info(self, category: str) -> Dict:
        """카테고리 정보 반환"""
        return self.categories.get(category, self.categories["Resources"])
    
    def get_history(self, limit: int = 10) -> list:
        """최근 분류 히스토리 반환"""
        return self.classification_history[-limit:]
    
    def reset(self):
        """분류기 리셋"""
        self.classification_history = []
        logger.info("PARAClassifier reset")


# 테스트용
if __name__ == "__main__":
    classifier = PARAClassifier()
    
    # 테스트 케이스
    test_texts = [
        ("마감이 11월 30일인 프로젝트 제안서", "project_proposal.txt"),
        ("Python 학습 자료 및 튜토리얼 모음", "learning_resources.md"),
        ("지난해 완료된 프로젝트 아카이브", "old_project_2024.txt"),
        ("API 문서 및 참고자료", "api_reference.pdf"),
    ]
    
    for text, filename in test_texts:
        result = classifier.classify_text(text, filename)
        print(f"\n📄 {filename}")
        print(f"   분류: {result['category']} ({result['confidence']:.0%})")
        print(f"   점수: {result['scores']}")



"""test_result(Phase5.2)

    cd backend/classifier
    python para_classifier.py

    📄 project_proposal.txt
        분류: Projects (50%)
        점수: {'Projects': 50.0, 'Areas': 0.0, 'Resources': 0.0, 'Archives': 0.0}

    📄 learning_resources.md
        분류: Resources (50%)
        점수: {'Projects': 0.0, 'Areas': 20.0, 'Resources': 50.0, 'Archives': 0.0}

    📄 old_project_2024.txt
        분류: Archives (50%)
        점수: {'Projects': 0.0, 'Areas': 0.0, 'Resources': 0.0, 'Archives': 50.0}

    📄 api_reference.pdf
        분류: Resources (40%)
        점수: {'Projects': 0.0, 'Areas': 0.0, 'Resources': 40.0, 'Archives': 0.0}

"""