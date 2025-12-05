# backend/services/rule_engine.py

"""
RuleEngine - 규칙 기반 분류 엔진
"""
import logging
import re
from typing import Dict, Any, List, Optional, Literal, TypedDict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

ParaCategory = Literal["Projects", "Areas", "Resources", "Archives"]


@dataclass
class RuleResult:
    """규칙 평가 결과"""
    category: ParaCategory
    confidence: float
    matched_rule: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Rule:
    """분류 규칙 정의"""
    name: str
    pattern: str  # 정규식 패턴 문자열
    category: ParaCategory
    confidence: float
    description: str
    _compiled_pattern: Optional[re.Pattern] = None

    @property
    def compiled_pattern(self) -> re.Pattern:
        """지연 컴파일된 정규식 패턴 반환"""
        if self._compiled_pattern is None:
            self._compiled_pattern = re.compile(self.pattern, re.IGNORECASE)
        return self._compiled_pattern


class RuleEngine:
    """
    정규식 패턴 및 메타데이터 규칙을 기반으로 문서를 분류합니다.
    """

    # 기본 PARA 규칙 정의 (15개 이상)
    _DEFAULT_RULES_DATA = [
        # Projects (목표, 마감일, 계획)
        {"name": "project_keyword", "pattern": r"\b(project|plan|roadmap|milestone)\b", "category": "Projects", "confidence": 0.7, "description": "Explicit project keywords"},
        {"name": "deadline_pattern", "pattern": r"(deadline|due date|target date):?\s*\d{4}-\d{2}-\d{2}", "category": "Projects", "confidence": 0.8, "description": "Deadline format"},
        {"name": "todo_list", "pattern": r"(-|\*)\s*\[\s*\]", "category": "Projects", "confidence": 0.6, "description": "Unchecked todo items"},
        {"name": "urgent_tag", "pattern": r"#urgent|#priority", "category": "Projects", "confidence": 0.75, "description": "Urgency tags"},
        {"name": "sprint_pattern", "pattern": r"\bsprint\s*\d+", "category": "Projects", "confidence": 0.7, "description": "Sprint numbering"},

        # Areas (지속적인 관리, 책임)
        {"name": "area_finance", "pattern": r"\b(finance|budget|invoice|tax|expense)\b", "category": "Areas", "confidence": 0.7, "description": "Finance related terms"},
        {"name": "area_health", "pattern": r"\b(health|workout|diet|medical|checkup)\b", "category": "Areas", "confidence": 0.7, "description": "Health related terms"},
        {"name": "area_study", "pattern": r"\b(study|learn|course|lecture|exam)\b", "category": "Areas", "confidence": 0.65, "description": "Study related terms"},
        {"name": "area_home", "pattern": r"\b(home|house|chore|maintenance|repair)\b", "category": "Areas", "confidence": 0.65, "description": "Home maintenance"},
        {"name": "routine_keyword", "pattern": r"\b(routine|daily|weekly|monthly|habit)\b", "category": "Areas", "confidence": 0.6, "description": "Routine activities"},

        # Resources (참고 자료, 정보)
        {"name": "resource_keyword", "pattern": r"\b(reference|guide|manual|tutorial|handbook)\b", "category": "Resources", "confidence": 0.7, "description": "Explicit resource keywords"},
        {"name": "note_keyword", "pattern": r"\b(note|memo|idea|thought|draft)\b", "category": "Resources", "confidence": 0.6, "description": "General notes"},
        {"name": "link_collection", "pattern": r"(https?://[^\s]+)", "category": "Resources", "confidence": 0.5, "description": "Contains URLs"},
        {"name": "code_snippet", "pattern": r"```[\s\S]*?```", "category": "Resources", "confidence": 0.6, "description": "Code blocks"},
        {"name": "book_ref", "pattern": r"\b(book|article|paper|citation)\b", "category": "Resources", "confidence": 0.65, "description": "Literature references"},

        # Archives (완료됨, 보관)
        {"name": "archive_keyword", "pattern": r"\b(archive|deprecated|obsolete|legacy)\b", "category": "Archives", "confidence": 0.8, "description": "Explicit archive keywords"},
        {"name": "completed_status", "pattern": r"\b(completed|done|finished|closed)\b", "category": "Archives", "confidence": 0.6, "description": "Completion status"},
        {"name": "old_year", "pattern": r"\b(20[0-1][0-9]|202[0-3])\b", "category": "Archives", "confidence": 0.5, "description": "Past years (context dependent)"},
    ]

    def __init__(self):
        """RuleEngine 초기화 및 규칙 로드"""
        self.rules: List[Rule] = []
        self._load_default_rules()

    def _load_default_rules(self):
        """기본 규칙 데이터를 Rule 객체로 변환하여 로드"""
        for rule_data in self._DEFAULT_RULES_DATA:
            try:
                self.rules.append(Rule(**rule_data))
            except TypeError as e:
                logger.error(f"Failed to load rule {rule_data.get('name')}: {e}")

    def evaluate(
        self, 
        text: str, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[RuleResult]:
        """
        텍스트와 메타데이터를 기반으로 규칙을 평가합니다.
        
        가장 높은 신뢰도를 가진 매칭 결과를 반환합니다.
        매칭되는 규칙이 없으면 None을 반환합니다.

        Args:
            text: 분석할 파일 내용
            metadata: 파일 메타데이터 (선택 사항)

        Returns:
            Optional[RuleResult]: 최고의 매칭 결과 또는 None
        """
        if not text:
            return None

        best_match: Optional[RuleResult] = None
        
        # 모든 규칙 순회
        for rule in self.rules:
            if rule.compiled_pattern.search(text):
                # 매칭 성공
                if best_match is None or rule.confidence > best_match.confidence:
                    best_match = RuleResult(
                        category=rule.category,
                        confidence=rule.confidence,
                        matched_rule=rule.name,
                        details={"description": rule.description}
                    )
        
        return best_match
