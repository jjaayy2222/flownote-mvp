# tests/test_prompt_conflict.py

import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
import requests

from backend.classifier.para_agent import PARAAgentState
from backend.classifier.para_classifier import PARAClassifier
from backend.classifier.para_agent_wrapper import run_para_agent_sync


from unittest.mock import patch, AsyncMock


def test_prompt_conflict(client):
    """
    애매한 내용이 담긴 텍스트를 분류하여 충돌 감지 및 최종 분류가 정상적으로 이루어지는지 테스트
    (TestClient 사용)
    """

    # 1. 애매한 내용이 담긴 임시 파일 내용 구성
    file_content = "Python 튜토리얼과 프로젝트 문서가 섞여 있는 애매한 케이스입니다."

    # 2. 파일 업로드 방식으로 요청
    files = {"file": ("python_tutorial.txt", file_content, "text/plain")}

    # Mocking: HybridClassifier
    with patch(
        "backend.classifier.hybrid_classifier.HybridClassifier.classify",
        new_callable=AsyncMock,
    ) as mock_hybrid:
        mock_hybrid.return_value = {
            "category": "Resources",
            "confidence": 0.6,
            "reasoning": "Mocked Reasoning",
            "snapshot_id": "mock_snapshot_123",
        }

        response = client.post(
            "/classifier/file",
            files=files,
        )

    # 기본 응답 검증
    assert (
        response.status_code == 200
    ), f"응답 코드 이상: {response.status_code}, body={response.text}"
    result = response.json()

    # 최신 통합 분류 구조에 맞춘 검증
    # 필수 키들 존재 여부
    for key in ["category", "confidence", "conflict_detected", "keyword_tags"]:
        assert key in result, f"{key} 없음: {result}"

    # PARA 4분류 안에서 나오는지 (Projects/Areas/Resources/Archives 가정)
    assert result["category"] in [
        "Projects",
        "Areas",
        "Resources",
        "Archives",
    ], f"잘못된 최종 카테고리: {result['category']}"

    # 신뢰도 범위 체크
    assert (
        0.0 <= result["confidence"] <= 1.0
    ), f"신뢰도 범위 이상: {result['confidence']}"

    # conflict_detected 가 bool 인지만 확인
    assert isinstance(
        result["conflict_detected"], bool
    ), f"conflict_detected 타입 이상: {result['conflict_detected']}"
