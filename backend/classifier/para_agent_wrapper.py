# backend/classifier/para_agent_wrapper.py

"""Async Para Agent를 Sync로 변환하는 래퍼"""

import asyncio
import logging
from typing import Any, Dict, Optional

from backend.classifier.para_agent import run_para_agent  # ← async 함수

logger = logging.getLogger(__name__)


def run_para_agent_sync(text: str, metadata: Optional[Dict] = None) -> Dict[str, Any]:
    """
    파라 에이전트의 Sync 버전
    FastAPI에서 직접 쓸 수 있음!
    """
    try:
        # 🔥 asyncio 이벤트 루프에서 async 함수 실행
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        result = loop.run_until_complete(
            run_para_agent(text=text, metadata=metadata or {})
        )

        loop.close()
        return result

    except Exception as e:
        logger.error(f"❌ Para Agent Error: {str(e)}")
        # Fallback: 기본 분류
        return {
            "category": "Resources",
            "keyword_tags": text.split()[:10],
            "confidence": 0.5,
            "conflict_detected": False,
            "resolution_method": "fallback",
        }


if __name__ == "__main__":
    # 테스트용
    test_text = """
    FlowNote는 AI 기반 문서 분류 도구입니다.
    프로젝트 관리, 메타데이터 추출, PARA 분류를 지원합니다.
    """

    result = run_para_agent_sync(test_text)
    print(f"✅ 분류 결과: {result}")


"""test_result_1 → ⭕️ (`python -m backend.classifier.para_agent_wrapper`)

    ✅ ModelConfig loaded from backend.config

    ================================================================================
    🔍 원본 LLM 응답:
    ================================================================================
    {
        "tags": ["업무"],
        "confidence": 0.75,
        "matched_keywords": {
            "업무": ["프로젝트"]
        },
        "reasoning": "프로젝트 관리와 관련된 키워드가 감지되어 업무 카테고리에 해당됨",
        "para_hints": {
            "업무": ["Projects"]
        }
    }
    ================================================================================

    📄 추출된 JSON:
    {
        "tags": ["업무"],
        "confidence": 0.75,
        "matched_keywords": {
            "업무": ["프로젝트"]
        },
        "reasoning": "프로젝트 관리와 관련된 키워드가 감지되어 업무 카테고리에 해당됨",
        "para_hints": {
            "업무": ["Projects"]
        }
    }

    ✅ 분류 결과: {'category': 'Resources', 'confidence': 0.9, 
                'snapshot_id': Snapshot(id='snap_20251104_131908', 
                timestamp=datetime.datetime(2025, 11, 4, 13, 19, 8, 484698), 
                text='\n    FlowNote는 AI 기반 문서 분류 도구입니다.\n    프로젝트 관리, 메타데이터 추출, PARA 분류를 지원합니다.\n    ', 
                para_result={'category': 'Resources', 'confidence': 0.9, 
                            'reasoning': "AI 기반 문서 분류 도구에 대한 설명으로, 참고 자료의 성격을 가지고 있으며, 
                            '문서 분류', '프로젝트 관리', '메타데이터 추출' 등의 정보 제공을 목적으로 하고 있음 → Resources 분류", 
                            'detected_cues': ['AI 기반', '문서 분류 도구', '지원'], 'source': 'langchain', 'has_metadata': False}, 
                keyword_result={'tags': ['업무'], 'confidence': 0.75, 'matched_keywords': {'업무': ['프로젝트']}, 
                                'reasoning': '프로젝트 관리와 관련된 키워드가 감지되어 업무 카테고리에 해당됨', 
                                'para_hints': {'업무': ['Projects']}}, 
                conflict_result={'final_category': 'Resources', 'para_category': 'Resources', 
                                'keyword_tags': ['업무'], 'confidence': 0.9, 'confidence_gap': 0.15, 
                                'conflict_detected': True, 'resolution_method': 'pending_user_review', 'requires_review': True, 
                                'para_reasoning': "AI 기반 문서 분류 도구에 대한 설명으로, 참고 자료의 성격을 가지고 있으며, 
                                '문서 분류', '프로젝트 관리', '메타데이터 추출' 등의 정보 제공을 목적으로 하고 있음 → Resources 분류", 
                                'reason': '모호한 상황 감지됨 (Gap: 0.15 < Threshold: 0.2)'}, 
                metadata={'confidence': 0, 'is_conflict': False, 'final_category': 'Resources'}), 
                'conflict_detected': True, 
                'requires_review': True, 
                'keyword_tags': ['업무'], 
                'reasoning': '모호한 상황 감지됨 (Gap: 0.15 < Threshold: 0.2)'}

"""


"""test_result_2 → ⭕️ 


    `python -c "from backend.classifier.para_agent_wrapper import run_para_agent_sync; result = run_para_agent_sync('FlowNote는 문서 분류 도구입니다'); print('✅ OK:', result)"`
    
    ✅ ModelConfig loaded from backend.config

    ================================================================================
    🔍 원본 LLM 응답:
    ================================================================================
    {
        "tags": ["기타"],
        "confidence": 0.30,
        "matched_keywords": {},
        "reasoning": "명확한 키워드가 감지되지 않음",
        "para_hints": {
            "기타": ["Resources"]
        }
    }
    ================================================================================

    📄 추출된 JSON:
    {
        "tags": ["기타"],
        "confidence": 0.30,
        "matched_keywords": {},
        "reasoning": "명확한 키워드가 감지되지 않음",
        "para_hints": {
            "기타": ["Resources"]
        }
    }

    ✅ OK: {
        'category': 'Resources', 
        'confidence': 0.9, 
        'snapshot_id': Snapshot(
            id='snap_20251104_132405', 
            timestamp=datetime.datetime(2025, 11, 4, 13, 24, 5, 14368), 
            text='FlowNote는 문서 분류 도구입니다', 
            para_result={
                'category': 'Resources', 
                'confidence': 0.9, 'reasoning': "FlowNote는 문서 분류 도구로, 참고 자료의 성격을 가지고 있어 Resources로 분류됨. '문서 분류 도구'라는 설명이 정보 제공의 성격을 나타냄.", 
                'detected_cues': ['문서', '분류', '도구'], 
                'source': 'langchain', 
                'has_metadata': False}, 
            keyword_result={
                'tags': ['기타'], 
                'confidence': 0.3, 
                'matched_keywords': {}, 
                'reasoning': '명확한 키워드가 감지되지 않음', 
                'para_hints': {'기타': ['Resources']}}, 
            conflict_result={
                'final_category': 'Resources', 
                'para_category': 'Resources', 
                'keyword_tags': ['기타'], 
                'confidence': 0.9, 
                'confidence_gap': 0.6, 
                'conflict_detected': False, 
                'resolution_method': 'auto_by_confidence', 
                'requires_review': False, 
                'winner_source': 'para', 
                'para_reasoning': "FlowNote는 문서 분류 도구로, 참고 자료의 성격을 가지고 있어 Resources로 분류됨. '문서 분류 도구'라는 설명이 정보 제공의 성격을 나타냄.", 
                'reason': '명확한 승자 선택됨 (Gap: 0.60)'}, 
            metadata={
                'confidence': 0, 
                'is_conflict': False, 
                'final_category': 'Resources'}), 
            'conflict_detected': False, 
            'requires_review': False, 
            'keyword_tags': ['기타'], 
            'reasoning': '명확한 승자 선택됨 (Gap: 0.60)'
            }

"""
