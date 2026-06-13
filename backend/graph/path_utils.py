# backend/graph/path_utils.py

"""
테넌트 격리형 그래프 파일 경로 생성 헬퍼 (Phase 4-1).

설계 원칙:
  - hashed_user_id 만을 파일명으로 사용 — user_id(PII) 절대 경로 노출 금지.
  - 경로 구조: {storage_base_path}/graph_data/{hashed_user_id}.graphml
  - 이 모듈은 IO를 수행하지 않는다 (경로 계산 전용).
"""

from __future__ import annotations

from pathlib import Path

# 그래프 파일이 위치할 서브디렉토리 (STORAGE_BASE_PATH 하위) — SSOT
_GRAPH_SUBDIR: str = "graph_data"

# 그래프 직렬화 파일 확장자 — 변경 시 이 상수 하나만 수정
_GRAPH_FILE_EXT: str = ".graphml"


def build_graph_path(hashed_user_id: str, storage_base_path: str) -> Path:
    """
    hashed_user_id와 STORAGE_BASE_PATH를 조합하여 결정론적 그래프 파일 경로를 반환한다.

    경로 구조:
        {storage_base_path}/graph_data/{hashed_user_id}.graphml

    보안 원칙:
        - hashed_user_id는 compute_hashed_user_id()의 반환값만 허용 (PII 미포함).
        - storage_base_path 값 자체는 절대 로그에 기록하지 않는다.

    Args:
        hashed_user_id   : SHA-256 해시된 사용자 식별자 (PII 미포함, 64자 hex)
        storage_base_path: STORAGE_BASE_PATH 환경 변수에서 로드된 루트 경로

    Returns:
        Path 객체 — 파일 생성 전 존재 여부 보장 없음 (ensure_graph_directory() 호출 필요)

    Raises:
        ValueError: hashed_user_id 또는 storage_base_path가 비어 있는 경우
    """
    if not hashed_user_id:
        raise ValueError("build_graph_path: 'hashed_user_id' must not be empty.")
    if not storage_base_path:
        raise ValueError("build_graph_path: 'storage_base_path' must not be empty.")

    return Path(storage_base_path) / _GRAPH_SUBDIR / f"{hashed_user_id}{_GRAPH_FILE_EXT}"
