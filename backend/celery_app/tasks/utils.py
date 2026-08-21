from typing import Any, Dict, Optional


def build_meta(base: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Dict[str, Any]:
    """로그 메타데이터 일관성 유지를 위한 공통 헬퍼 함수"""
    return (base or {}) | kwargs
