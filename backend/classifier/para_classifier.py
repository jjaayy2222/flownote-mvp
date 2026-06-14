# backend/classifier/para_classifier.py

"""
PARA 분류기 - LangChain 기반
텍스트를 Projects, Areas, Resources, Archives로 분류
상대경로 + Fallback 시스템 포함
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

prompt_path = Path(__file__).parent / "prompts" / "para_system.txt"

# from langchain_integration import classify_with_langchain
from backend.classifier.langchain_integration import classify_with_langchain

logger = logging.getLogger(__name__)


class PARAClassifier:
    """
    PARA 시스템 기반 자동 분류 클래스 (LangChain 통합)

    Projects: 명확한 기한과 목표가 있는 작업
    Areas: 지속적으로 관심있는 영역
    Resources: 참고용 자료/정보
    Archives: 완료되었거나 더 이상 사용하지 않는 것
    """

    CATEGORIES = {
        "Projects": {
            "icon": "📋",
            "color": "#3498db",
            "description": "명확한 기한과 목표가 있는 작업",
        },
        "Areas": {
            "icon": "🎯",
            "color": "#2ecc71",
            "description": "지속적으로 관심있는 영역",
        },
        "Resources": {
            "icon": "📚",
            "color": "#f39c12",
            "description": "참고용 자료 및 정보",
        },
        "Archives": {
            "icon": "📦",
            "color": "#95a5a6",
            "description": "완료되었거나 미사용 항목",
        },
    }

    def __init__(self, use_langchain: bool = True):
        """
        분류기 초기화

        Args:
            use_langchain: LangChain 사용 여부 (기본: True)
        """
        self.categories = self.CATEGORIES
        self.classification_history = []
        self.use_langchain = use_langchain
        logger.info(f"PARAClassifier initialized (LangChain: {use_langchain})")

    def classify_text(
        self,
        text: str,
        filename: str = "unknown",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict:
        """
        텍스트를 PARA 카테고리로 분류

        Args:
            text (str): 분류할 텍스트
            filename (str): 파일명 (참고용)
            metadata (Optional[Dict]): 메타데이터 (미래 대비)

        Returns:
            Dict: 분류 결과
        """

        if not text or not isinstance(text, str):
            logger.warning(f"Invalid text input for {filename}")
            return {
                "category": "Resources",
                "confidence": 0.0,
                "reason": "Invalid input",
                "filename": filename,
            }

        try:
            # LangChain으로 분류
            if self.use_langchain:
                result = classify_with_langchain(text, metadata=metadata)

                classification_result = {
                    "category": result["category"],
                    "confidence": result["confidence"],
                    "reasoning": result["reasoning"],
                    "detected_cues": result.get("detected_cues", []),
                    "timestamp": datetime.now().isoformat(),
                    "filename": filename,
                    "source": "langchain",
                    "has_metadata": result.get("has_metadata", False),
                }
            else:
                # 폴백: 키워드 기반 (STEP 5.2.1)
                scores = self._calculate_scores_fallback(text.lower(), filename)
                best_category = max(scores.items(), key=lambda x: x[1])

                classification_result = {
                    "category": best_category[0],
                    "confidence": min(best_category[1] / 100, 1.0),
                    "scores": scores,
                    "timestamp": datetime.now().isoformat(),
                    "filename": filename,
                    "source": "keyword",
                }

            # 히스토리 저장
            self._save_to_history(classification_result)

            logger.info(
                f"Classified '{filename}' as '{classification_result['category']}' "
                f"(confidence: {classification_result['confidence']:.2%})"
            )

            return classification_result

        except Exception as e:
            logger.error(f"분류 중 오류 발생: {str(e)}")
            # 에러 시 Resources로 폴백
            return {
                "category": "Resources",
                "confidence": 0.0,
                "reason": f"Error: {str(e)}",
                "filename": filename,
                "source": "error",
            }

    def _calculate_scores_fallback(self, text: str, filename: str) -> Dict[str, float]:
        """
        키워드 기반 점수 계산 (LangChain 실패 시 폴백)
        """
        scores = {"Projects": 0.0, "Areas": 0.0, "Resources": 0.0, "Archives": 0.0}

        # Projects 키워드
        project_keywords = [
            "deadline",
            "due date",
            "goal",
            "target",
            "task",
            "sprint",
            "마감",
            "목표",
            "과제",
            "계획",
            "진행",
            "구현",
            "배포",
        ]

        # Areas 키워드
        area_keywords = [
            "learning",
            "skill",
            "development",
            "improvement",
            "habit",
            "관리",
            "유지",
            "개선",
            "학습",
            "기술",
            "지속",
            "반복",
        ]

        # Resources 키워드
        resource_keywords = [
            "reference",
            "guide",
            "tutorial",
            "documentation",
            "template",
            "참고",
            "자료",
            "가이드",
            "설명서",
            "정보",
            "모음",
        ]

        # Archives 키워드
        archive_keywords = [
            "completed",
            "finished",
            "done",
            "old",
            "deprecated",
            "archived",
            "완료",
            "끝",
            "구식",
            "보관",
            "미사용",
            "2024",
            "2023",
        ]

        scores["Projects"] += self._count_keywords(text, project_keywords) * 20
        scores["Areas"] += self._count_keywords(text, area_keywords) * 20
        scores["Resources"] += self._count_keywords(text, resource_keywords) * 20
        scores["Archives"] += self._count_keywords(text, archive_keywords) * 20

        # 파일명 기반 추가
        filename_lower = filename.lower()
        if "archive" in filename_lower or "old" in filename_lower:
            scores["Archives"] += 30
        elif "resource" in filename_lower or "guide" in filename_lower:
            scores["Resources"] += 30
        elif "project" in filename_lower or "task" in filename_lower:
            scores["Projects"] += 30

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
    logging.basicConfig(level=logging.INFO)

    classifier = PARAClassifier(use_langchain=True)

    # 테스트 케이스
    test_texts = [
        ("마감이 11월 30일인 프로젝트 제안서", "project_proposal.txt"),
        ("Python 학습 자료 및 튜토리얼 모음", "learning_resources.md"),
        ("지난해 완료된 프로젝트 아카이브", "old_project_2024.txt"),
        ("API 문서 및 참고자료", "api_reference.pdf"),
    ]

    print("=" * 60)
    print("PARA 분류기 테스트 (LangChain 통합)")
    print("=" * 60)

    for text, filename in test_texts:
        result = classifier.classify_text(text, filename)
        print(f"\n📄 {filename}")
        print(f"   분류: {result['category']} ({result['confidence']:.0%})")
        print(f"   근거: {result.get('reasoning', 'N/A')}")
        print(f"   단서: {', '.join(result.get('detected_cues', [])[:3])}")


"""test_result(Phase5.2.1)

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


"""test_result(Phase5.2.2)

    python backend/classifier/para_classifier.py
    
    ✅ ModelConfig loaded from backend.config

    INFO:__main__:PARAClassifier initialized (LangChain: True)
    ============================================================
    PARA 분류기 테스트 (LangChain 통합)
    ============================================================
    
    INFO:httpx:HTTP Request: POST https:**** "HTTP/1.1 200 OK"
    INFO:langchain_integration:분류 완료: Projects (confidence: 100.00%, metadata: False)
    INFO:__main__:Classified 'project_proposal.txt' as 'Projects' (confidence: 100.00%)

    📄 project_proposal.txt
        분류: Projects (100%)
        근거: 마감일(11월 30일)과 구체적 목표(프로젝트 제안서)로 인해 Projects로 분류됨.
        단서: 마감, 프로젝트, 제안서

    INFO:httpx:HTTP Request: POST https:**** "HTTP/1.1 200 OK"
    INFO:langchain_integration:분류 완료: Resources (confidence: 95.00%, metadata: False)
    INFO:__main__:Classified 'learning_resources.md' as 'Resources' (confidence: 95.00%)

    📄 learning_resources.md
        분류: Resources (95%)
        근거: 참고 자료로서 '학습 자료'와 '튜토리얼'이라는 표현이 포함되어 있어 Resources로 분류됨.
        단서: 학습 자료, 튜토리얼, 모음

    INFO:httpx:HTTP Request: POST https:**** "HTTP/1.1 200 OK"
    INFO:langchain_integration:분류 완료: Archives (confidence: 100.00%, metadata: False)
    INFO:__main__:Classified 'old_project_2024.txt' as 'Archives' (confidence: 100.00%)

    📄 old_project_2024.txt
        분류: Archives (100%)
        근거: 완료 표현(완료된)과 과거형 표기(지난해)로 인해 Archives로 분류됨.
        단서: 완료, 지난해, 아카이브

    INFO:httpx:HTTP Request: POST https:**** "HTTP/1.1 200 OK"
    INFO:langchain_integration:분류 완료: Resources (confidence: 90.00%, metadata: False)
    INFO:__main__:Classified 'api_reference.pdf' as 'Resources' (confidence: 90.00%)

    📄 api_reference.pdf
        분류: Resources (90%)
        근거: 참고 자료와 관련된 내용으로, '문서'와 '참고자료'라는 키워드가 포함되어 있어 Resources로 분류됨.
        단서: API 문서, 참고자료

"""
