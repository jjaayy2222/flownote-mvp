# backend/services/feature_extractor.py

"""
FeatureExtractor - 파일 특성 추출
"""
import logging
import re
from typing import Dict, Any, List
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

# 상수 정의 (컴파일된 정규식)
_MISSING_DAYS_DEFAULT = 999
_WORD_TOKEN_RE = re.compile(r"\b\w+\b")
_CHECKLIST_RE = re.compile(r"[-*]\s*\[\s*[xX\s]\s*\]")
_DEADLINE_RE = re.compile(r"\d{4}-\d{2}-\d{2}|deadline|due date", re.IGNORECASE)


@dataclass
class FileFeatures:
    """추출된 파일 특징"""
    # 텍스트 특징
    text_length: int
    word_count: int
    unique_words: int
    avg_word_length: float
    
    # 구조 특징
    has_deadline: bool
    has_checklist: bool
    has_code_block: bool
    
    # 시간 특징
    days_since_access: int
    days_since_edit: int
    access_frequency: float
    edit_frequency: float
    
    # 관계 특징
    reference_count: int
    tag_count: int
    
    # 감정 특징
    sentiment_score: float
    urgency_indicators: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return asdict(self)


class FeatureExtractor:
    """파일 특징 추출기"""

    def __init__(self):
        self.urgency_keywords = [
            "urgent", "asap", "critical", "emergency", "deadline",
            "immediately", "important", "priority", "due date"
        ]
        
        self.sentiment_positive = [
            "good", "great", "excellent", "success", "complete", "done",
            "fixed", "resolved", "happy", "best"
        ]
        
        self.sentiment_negative = [
            "bad", "terrible", "failed", "broken", "issue", "bug",
            "error", "problem", "wrong", "fail"
        ]

    def extract(
        self,
        file_content: str,
        file_metadata: Dict[str, Any],
        usage_stats: Dict[str, Any]
    ) -> FileFeatures:
        """파일에서 특징 추출 (Synchronous)"""
        try:
            # 텍스트 분석
            text_features = self._analyze_text(file_content)
            
            # 구조 분석
            structure_features = self._analyze_structure(file_content, file_metadata)
            
            # 시간 분석
            temporal_features = self._analyze_temporal(usage_stats)
            
            # 관계 분석
            relationship_features = self._analyze_relationships(file_metadata)
            
            # 감정 분석
            sentiment_features = self._analyze_sentiment(file_content)
            
            return FileFeatures(
                **text_features,
                **structure_features,
                **temporal_features,
                **relationship_features,
                **sentiment_features
            )

        except Exception as e:
            # 에러 로깅 강화 (Stack Trace 포함)
            logger.error(f"Feature extraction failed: {str(e)}", exc_info=True)
            return self._default_features()

    def _tokenize_words(self, text: str) -> List[str]:
        """
        단어 토큰화 헬퍼 함수
        
        Note: 현재는 간단한 정규식(\b\w+\b)을 사용하여 문장부호를 제거하고 단어를 추출합니다.
        다국어(CJK 등) 처리나 복잡한 토큰화가 필요한 경우, 이 함수를 확장하거나 
        별도의 NLP 라이브러리를 도입해야 합니다.
        """
        return _WORD_TOKEN_RE.findall(text.lower()) if text else []

    def _analyze_text(self, text: str) -> Dict[str, Any]:
        """텍스트 특징 분석"""
        if not text:
            return {
                "text_length": 0,
                "word_count": 0,
                "unique_words": 0,
                "avg_word_length": 0.0,
            }
            
        text_clean = text.strip()
        words = self._tokenize_words(text_clean)
        word_count = len(words)
        
        return {
            "text_length": len(text_clean),
            "word_count": word_count,
            "unique_words": len(set(words)),
            "avg_word_length": sum(len(w) for w in words) / word_count if word_count > 0 else 0.0,
        }

    def _analyze_structure(self, text: str, metadata: Dict) -> Dict[str, Any]:
        """구조 특징 분석"""
        if not text:
            # 텍스트가 없어도 메타데이터의 deadline은 확인해야 함
            has_deadline = bool(metadata.get("deadline"))
            return {
                "has_deadline": has_deadline,
                "has_checklist": False,
                "has_code_block": False,
            }

        # 체크리스트 패턴: - [ ] 또는 * [x] (다양한 공백 지원)
        has_checklist = bool(_CHECKLIST_RE.search(text))
        
        # 코드 블록: ```
        has_code_block = '```' in text
        
        # 마감일: 메타데이터 또는 텍스트 내 패턴
        # _DEADLINE_RE는 IGNORECASE로 컴파일되었으므로 text.lower() 불필요하지만,
        # 다른 부분과의 일관성을 위해 text 자체를 넘김 (search는 부분 매칭)
        has_deadline = bool(metadata.get("deadline")) or bool(_DEADLINE_RE.search(text))
        
        return {
            "has_deadline": has_deadline,
            "has_checklist": has_checklist,
            "has_code_block": has_code_block,
        }

    def _analyze_temporal(self, usage_stats: Dict) -> Dict[str, Any]:
        """시간 특징 분석"""
        days_since_access = usage_stats.get("days_since_access", _MISSING_DAYS_DEFAULT)
        days_since_edit = usage_stats.get("days_since_edit", _MISSING_DAYS_DEFAULT)
        
        # 비정상적인 음수값은 결측치로 간주하여 큰 기본값으로 클램핑
        if days_since_access < 0:
            days_since_access = _MISSING_DAYS_DEFAULT
        if days_since_edit < 0:
            days_since_edit = _MISSING_DAYS_DEFAULT
            
        # 카운트 값도 음수일 수 없으므로 0으로 클램핑
        access_count = max(0, usage_stats.get("access_count", 0))
        edit_count = max(0, usage_stats.get("edit_count", 0))
        
        # 0으로 나누기 방지
        access_denom = days_since_access + 1
        edit_denom = days_since_edit + 1
        
        access_frequency = access_count / access_denom
        edit_frequency = edit_count / edit_denom
        
        return {
            "days_since_access": days_since_access,
            "days_since_edit": days_since_edit,
            "access_frequency": round(access_frequency, 3),
            "edit_frequency": round(edit_frequency, 3),
        }

    def _analyze_relationships(self, metadata: Dict) -> Dict[str, Any]:
        """관계 특징 분석"""
        return {
            "reference_count": metadata.get("reference_count", 0),
            "tag_count": len(metadata.get("tags", [])),
        }

    def _analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """감정 및 긴급성 분석"""
        if not text:
            return {
                "sentiment_score": 0.0,
                "urgency_indicators": [],
            }
            
        text_lower = text.lower()
        words = self._tokenize_words(text_lower)
        
        # sum() 단순화 (bool -> int 자동 변환 활용)
        positive_count = sum(w in self.sentiment_positive for w in words)
        negative_count = sum(w in self.sentiment_negative for w in words)
        total = positive_count + negative_count
        
        sentiment_score = (positive_count - negative_count) / total if total > 0 else 0.0
        
        urgency_indicators = [
            kw for kw in self.urgency_keywords 
            if kw in text_lower
        ]
        
        return {
            "sentiment_score": round(sentiment_score, 2),
            "urgency_indicators": urgency_indicators,
        }

    def _default_features(self) -> FileFeatures:
        """기본 특징값 (에러 시 반환)"""
        return FileFeatures(
            text_length=0,
            word_count=0,
            unique_words=0,
            avg_word_length=0.0,
            has_deadline=False,
            has_checklist=False,
            has_code_block=False,
            days_since_access=_MISSING_DAYS_DEFAULT,
            days_since_edit=_MISSING_DAYS_DEFAULT,
            access_frequency=0.0,
            edit_frequency=0.0,
            reference_count=0,
            tag_count=0,
            sentiment_score=0.0,
            urgency_indicators=[],
        )
