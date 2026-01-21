# backend/services/compression_service.py

import gzip
import logging
from typing import Union, Tuple

from backend.config import WebSocketConfig

logger = logging.getLogger(__name__)

# 압축 적용 임계값 (설정에서 로드)
COMPRESSION_THRESHOLD = WebSocketConfig.COMPRESSION_THRESHOLD


def compress_payload(payload: str) -> Tuple[Union[str, bytes], bool]:
    """
    메시지 페이로드 크기가 임계값을 초과하면 gzip 압축을 수행합니다.

    Args:
        payload: 전송할 메시지 문자열 (JSON 등)

    Returns:
        Tuple[Union[str, bytes], bool]: (처리된 데이터, 압축 여부)
    """
    # 텍스트 데이터를 UTF-8 바이트로 인코딩
    data_bytes = payload.encode("utf-8")

    # 임계값 확인
    if len(data_bytes) > COMPRESSION_THRESHOLD:
        try:
            compressed = gzip.compress(data_bytes)
            # 압축 효율이 없는 경우 (오히려 커지는 경우) 고려
            if len(compressed) < len(data_bytes):
                logger.debug(
                    f"Payload compressed: {len(data_bytes)} -> {len(compressed)} bytes "
                    f"({(1 - len(compressed)/len(data_bytes))*100:.1f}% reduced)"
                )
                return compressed, True
        except Exception as e:
            logger.error(f"Compression failed: {e}")

    return payload, False
