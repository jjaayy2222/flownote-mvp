# tests/unit/classifier/test_ai_classifier.py

import pytest
import json
from unittest.mock import MagicMock
from backend.classifier.ai_classifier import AIClassifier
from backend.services.gpt_helper import GPT4oHelper


@pytest.fixture
def mock_gpt_helper():
    return MagicMock(spec=GPT4oHelper)


@pytest.fixture
def classifier(mock_gpt_helper):
    return AIClassifier(gpt_helper=mock_gpt_helper)


@pytest.mark.asyncio
async def test_classify_success(classifier, mock_gpt_helper):
    """정상적인 분류 성공 케이스"""
    mock_response = {
        "category": "Projects",
        "confidence": 0.9,
        "reason": "This is a project related text",
        "keywords": ["project", "plan"],
    }
    # _call은 동기 메서드이므로 일반 return_value 설정 (asyncio.to_thread가 처리)
    mock_gpt_helper._call.return_value = json.dumps(mock_response)

    result = await classifier.classify("Our Q4 project plan")

    assert result["category"] == "Projects"
    assert result["confidence"] == 0.9
    assert result["reasoning"] == "This is a project related text"
    assert "keywords" in result


@pytest.mark.asyncio
async def test_classify_empty_text(classifier):
    """빈 텍스트 입력 시 처리"""
    result = await classifier.classify("")

    assert result["category"] == "Unclassified"
    assert result["confidence"] == 0.0
    assert "Input text is empty" in result["reasoning"]


@pytest.mark.asyncio
async def test_classify_json_parsing_error(classifier, mock_gpt_helper):
    """GPT 응답이 유효한 JSON이 아닌 경우"""
    mock_gpt_helper._call.return_value = "Not a JSON string"

    result = await classifier.classify("some text")

    assert result["category"] == "Unclassified"
    assert result["confidence"] == 0.0
    assert "JSON parsing failed" in result["reasoning"]


@pytest.mark.asyncio
async def test_classify_api_error(classifier, mock_gpt_helper):
    """GPT API 호출 중 에러 발생"""
    # 동기 메서드에서 예외 발생
    mock_gpt_helper._call.side_effect = Exception("API Error")

    result = await classifier.classify("some text")

    assert result["category"] == "Unclassified"
    assert result["confidence"] == 0.0
    assert "API Error" in result["reasoning"]


@pytest.mark.asyncio
async def test_classify_markdown_json(classifier, mock_gpt_helper):
    """마크다운 코드 블록으로 감싸진 JSON 응답 처리"""
    json_str = json.dumps(
        {
            "category": "Areas",
            "confidence": 0.8,
            "reason": "Health related",
            "keywords": ["health"],
        }
    )
    markdown_response = f"```json\n{json_str}\n```"
    mock_gpt_helper._call.return_value = markdown_response

    result = await classifier.classify("Daily workout")

    assert result["category"] == "Areas"
    assert result["confidence"] == 0.8


@pytest.mark.asyncio
async def test_classify_with_context(classifier, mock_gpt_helper):
    """컨텍스트가 포함된 분류 요청"""
    mock_gpt_helper._call.return_value = '{"category": "Resources"}'
    context = {"user_id": "123", "recent_files": ["note.md"]}

    await classifier.classify("some text", context=context)

    # 호출 시 context가 user_message(prompt)에 포함되었는지 확인
    call_args = mock_gpt_helper._call.call_args
    assert "Context:" in call_args.kwargs["prompt"]
    assert "note.md" in call_args.kwargs["prompt"]
