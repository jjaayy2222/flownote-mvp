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

    Returns:
        성공적으로 저장된 파일의 절대 경로
    """
    absolute_path = os.path.abspath(output_filepath)
    os.makedirs(os.path.dirname(absolute_path), exist_ok=True)

    try:
        with open(absolute_path, "w", encoding="utf-8") as f:
            for item in dataset:
                # 불변성 유지를 위해 얕은 복사 수행
                item_copy = item.copy()

                # PII 필드 대상 마스킹 적용 (backend.utils.mask_pii_id 재사용)
                if pii_fields:
                    for field in pii_fields:
                        if field in item_copy:
                            # 문자열인 경우에만 해시 마스킹 (숫자나 객체는 별도 처리 필요)
                            val = item_copy[field]
                            item_copy[field] = mask_pii_id(str(val)) if val else val

                # JSON 직렬화 (유니코드 문자 보존)
                json_line = json.dumps(item_copy, ensure_ascii=False)
                f.write(json_line + "\n")

        logger.info(
            "Successfully serialized dataset to JSONL",
            extra={
                "filepath": absolute_path,
                "total_items": len(dataset),
                "masked_fields": pii_fields,
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
