# backend/utils/finetune_parser.py

"""
FlowNote MVP - Fine-tuning Dataset Parser Module (파인튜닝 데이터셋 파서).

[KO] RAG 데이터셋을 OpenAI Fine-tuning 형식으로 변환 및 직렬화하고 PII(개인정보)를 마스킹합니다.
[EN] Formats and serializes RAG datasets into OpenAI Fine-tuning format, with recursive PII masking capabilities.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional, Set

from backend.utils import mask_pii_id

logger = logging.getLogger(__name__)


def format_finetune_message(
    question: str,
    answer: str,
    system_prompt: str = "You are a helpful AI assistant that answers questions based on the provided context.",
) -> Dict[str, List[Dict[str, str]]]:
    """
    [KO] RAG 검색 컨텍스트(Q)와 LLM 생성 응답(A)을 OpenAI Chat Fine-tuning 포맷으로 변환합니다.
    [EN] Formats RAG query context (Q) and LLM generated response (A) into OpenAI Chat Fine-tuning format.

    Args:
        question: [KO] 사용자 질문 및 RAG 컨텍스트. [EN] User question and RAG context.
        answer: [KO] LLM 생성 응답. [EN] LLM generated response.
        system_prompt: [KO] 시스템 프롬프트 (옵션). [EN] System prompt (optional).

    Returns:
        [KO] OpenAI Fine-tuning JSON 포맷 ({"messages": [...]}).
        [EN] OpenAI Fine-tuning JSON format ({"messages": [...]}).
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


def _mask_nested_pii(data: Any, pii_fields: Set[str]) -> Any:
    """
    [KO] 딕셔너리와 컨테이너를 재귀적으로 탐색하여 지정된 PII 필드를 찾아 안전하게 마스킹합니다.
    [EN] Recursively searches dicts and containers to find and safely mask specified PII fields.

    Args:
        data: [KO] 탐색할 데이터 구조. [EN] The data structure to traverse.
        pii_fields: [KO] 마스킹할 키 집합. [EN] Set of keys to mask.

    Returns:
        [KO] 마스킹 처리가 완료된 새로운 데이터 구조.
        [EN] The masked new data structure.
    """
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            # 값이 딕셔너리, 리스트, 튜플, 세트 등 내부 구조를 가지면 강제 문자열 변환 없이 재귀 진입
            if isinstance(v, (dict, list, tuple, set)):
                result[k] = _mask_nested_pii(v, pii_fields)
            # pii_fields에 해당하고 값이 스칼라(None 제외)일 때만 마스킹
            elif k in pii_fields and v is not None:
                result[k] = mask_pii_id(str(v))
            else:
                result[k] = v
        return result
    elif isinstance(data, (list, tuple, set)):
        # 참고: JSON 명세는 set(집합)을 네이티브 배열 타입으로 지원하지 않습니다.
        # 이를 무방비로 직렬화하면 단순 문자열 "{x, y}" 형태로 데이터 구조가 오염될 수 있습니다.
        # 향후 학습 파이프라인에서 예측 가능하고 일관된 JSON 배열([]) 형태로
        # 구조를 보존하기 위해, 여기서 의도적으로 set을 list로 정규화합니다.
        container_type = list if isinstance(data, set) else type(data)
        return container_type(_mask_nested_pii(item, pii_fields) for item in data)
    else:
        return data


def serialize_to_jsonl(
    dataset: List[Dict[str, Any]],
    output_filepath: str,
    pii_fields: Optional[List[str]] = None,
    strict_alert: bool = False,
) -> str:
    """
    [KO] 데이터셋을 .jsonl 파일로 직렬화하며, 필요한 경우 지정된 PII 필드들을 안전하게 마스킹 처리합니다.
    [EN] Serializes the dataset to a .jsonl file, safely masking specified PII fields if needed.

    Args:
        dataset: [KO] 변환된 OpenAI Fine-tuning 포맷 데이터셋 리스트. [EN] Transformed dataset in OpenAI Fine-tuning format.
        output_filepath: [KO] 저장할 jsonl 파일의 대상 경로. [EN] Target path of the output jsonl file.
        pii_fields: [KO] 마스킹을 적용할 딕셔너리 필드 목록 (중첩 구조 포함). [EN] List of dict keys to mask (including nested structures).
        strict_alert: [KO] True일 경우 직렬화 실패 시 [OBS] Warning 알람 발생. [EN] If True, triggers an [OBS] Warning alert on serialization fallback.

    Returns:
        [KO] 성공적으로 저장된 파일의 절대 경로.
        [EN] The absolute path of the successfully saved file.
    """
    absolute_path = os.path.abspath(output_filepath)
    os.makedirs(os.path.dirname(absolute_path), exist_ok=True)

    try:
        pii_fields_set = set(pii_fields) if pii_fields else set()

        fallback_counts: Dict[str, int] = {}

        # Dataclass, datetime 등 비-직렬화 객체 발생으로 인한 런타임 에러 방지용 안전 장치
        # (주의: 대규모 데이터셋 처리 시 I/O 부하와 로그 스팸을 방지하기 위해
        # 여기서 개별 건마다 직접 로깅하지 않고, 타입별 발생 횟수만 집계하여 최종 요약합니다.)
        def _json_fallback(obj: Any) -> str:
            obj_type = type(obj).__name__
            fallback_counts[obj_type] = fallback_counts.get(obj_type, 0) + 1
            return str(obj)

        with open(absolute_path, "w", encoding="utf-8") as f:
            for item in dataset:
                # PII 필드 대상 재귀적 깊은 마스킹 적용 (backend.utils.mask_pii_id 재사용)
                # _mask_nested_pii 함수를 통해 원본을 훼손하지 않는 새 딕셔너리 반환 보장
                masked_item = _mask_nested_pii(item, pii_fields_set)

                # JSON 직렬화 (유니코드 문자 보존 및 비-직렬화 객체 문자열 변환 처리)
                json_line = json.dumps(
                    masked_item, ensure_ascii=False, default=_json_fallback
                )
                f.write(json_line + "\n")

        if fallback_counts:
            # 개별 객체 단위의 시끄러운 로그 대신, 단일 요약본으로 운영상의 가시성과 성능을 동시 확보
            # 운영자 디버깅 향상을 위한 추가 컨텍스트(filepath, total_items 등) 포함
            extra_payload = {
                "fallback_counts": fallback_counts,
                "filepath": absolute_path,
                "total_items": len(dataset),
            }

            if strict_alert:
                logger.warning(
                    "[OBS] Non-serializable types encountered during JSONL serialization (fallback applied).",
                    extra=extra_payload,
                )
            else:
                logger.info(
                    "Non-serializable types encountered during JSONL serialization (fallback applied).",
                    extra=extra_payload,
                )

        logger.info(
            "Successfully serialized dataset to JSONL",
            extra={
                "filepath": absolute_path,
                "total_items": len(dataset),
                "masked_fields": list(pii_fields_set) or None,
                "fallback_occurrences": fallback_counts or None,
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
