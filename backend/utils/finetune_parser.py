# backend/utils/finetune_parser.py

import json
import logging
import os
from typing import Any, Dict, List, Optional

from backend.utils import mask_pii_id

logger = logging.getLogger(__name__)


def format_finetune_message(
    question: str,
    answer: str,
    system_prompt: str = "You are a helpful AI assistant that answers questions based on the provided context.",
) -> Dict[str, List[Dict[str, str]]]:
    """
    RAG 검색 컨텍스트(Q)와 LLM 생성 응답(A)을 OpenAI Chat Fine-tuning 포맷으로 변환합니다.

    Args:
        question: 사용자 질문 및 RAG 컨텍스트 (Q)
        answer: LLM 생성 응답 (A)
        system_prompt: 시스템 프롬프트 (옵션)

    Returns:
        OpenAI Fine-tuning JSON 포맷 ({"messages": [...]})
    """
    # 사용자의 질문이나 응답 내에 있는 PII성 식별자(보통 이메일이나, 특정 패턴)를
    # 마스킹하는 로직이 필요한 경우 여기서 처리할 수 있습니다.
    # 현재는 구조 변환만 수행하며, 식별자 자체의 마스킹은 직렬화 등 별도로 적용 가능합니다.
    return {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ]
    }


def _mask_nested_pii(data: Any, pii_fields: set[str]) -> Any:
    """
    딕셔너리와 리스트를 재귀적으로 탐색하여 pii_fields에 지정된 키를 찾아 안전하게 마스킹합니다.
    (스칼라 값만 마스킹 처리하여 딕셔너리/리스트 등 중첩 구조 파괴를 방지합니다.)
    """
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            # 값이 딕셔너리나 리스트 등 내부 구조를 가지면 강제 문자열 변환 없이 재귀 진입
            if isinstance(v, (dict, list)):
                result[k] = _mask_nested_pii(v, pii_fields)
            # pii_fields에 해당하고 값이 스칼라(None 제외)일 때만 마스킹
            elif k in pii_fields and v is not None:
                result[k] = mask_pii_id(str(v))
            else:
                result[k] = v
        return result
    elif isinstance(data, list):
        return [_mask_nested_pii(item, pii_fields) for item in data]
    else:
        return data


def serialize_to_jsonl(
    dataset: List[Dict[str, Any]],
    output_filepath: str,
    pii_fields: Optional[List[str]] = None,
) -> str:
    """
    데이터셋을 .jsonl 파일로 직렬화하며, 필요한 경우 지정된 PII 필드들을 안전하게 마스킹 처리합니다.

    Args:
        dataset: 변환된 OpenAI Fine-tuning 포맷 데이터셋 리스트
        output_filepath: 저장할 jsonl 파일의 대상 경로
        pii_fields: 값에 마스킹을 적용할 딕셔너리 필드 목록 (예: ["session_id", "user_id"])
                    (중첩된 구조 내부의 필드 깊이와 관계없이 재귀적으로 찾아 마스킹함)

    Returns:
        성공적으로 저장된 파일의 절대 경로
    """
    absolute_path = os.path.abspath(output_filepath)
    os.makedirs(os.path.dirname(absolute_path), exist_ok=True)

    try:
        pii_fields_set = set(pii_fields) if pii_fields else set()
        
        # Dataclass, datetime 등 비-직렬화 객체 발생으로 인한 런타임 에러 방지용 안전 장치
        def _json_fallback(obj: Any) -> str:
            return str(obj)
        
        with open(absolute_path, "w", encoding="utf-8") as f:
            for item in dataset:
                # PII 필드 대상 재귀적 깊은 마스킹 적용 (backend.utils.mask_pii_id 재사용)
                # _mask_nested_pii 함수를 통해 원본을 훼손하지 않는 새 딕셔너리 반환 보장
                masked_item = _mask_nested_pii(item, pii_fields_set)

                # JSON 직렬화 (유니코드 문자 보존 및 비-직렬화 객체 문자열 변환 처리)
                json_line = json.dumps(masked_item, ensure_ascii=False, default=_json_fallback)
                f.write(json_line + "\n")

        logger.info(
            "Successfully serialized dataset to JSONL",
            extra={
                "filepath": absolute_path,
                "total_items": len(dataset),
                "masked_fields": list(pii_fields_set) if pii_fields_set else None,
            },
        )
        return absolute_path

    except Exception as e:
        logger.error(
            "Failed to serialize dataset to JSONL",
            extra={
                "filepath": absolute_path,
                "error": str(e),
            },
        )
        raise
