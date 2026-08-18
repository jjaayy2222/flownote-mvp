"""
에이전트 파이프라인(Agent Pipeline) 전역에서 공유되는 공통 상수를 정의합니다.
유틸리티(utils)나 노드(nodes) 모듈 간의 순환 참조(Circular Import)를 구조적으로
차단하고, 단일 진실 공급원(Single Source of Truth)을 유지하기 위해 사용됩니다.
"""

from typing import Final

# 하이브리드 검색에서 빈 결과를 명확히 표현하는 공용 상수 (매직 스트링 제거)
# [주요 참조처 (Consumers)]
# 1. backend.agent.nodes.retrieve_node: 빈 키워드에 대한 단락 평가(Short-circuit) 시 즉시 반환
# 2. backend.agent.utils.search_similar_docs: 빈 키워드 폴백 로직 내 반환
# ※ 향후 "검색 결과 없음"의 표현 형식이 바뀔 경우, 파편화 방지를 위해 반드시 이 상수만을 수정해야 합니다.
EMPTY_RETRIEVED_CONTEXT: Final[str] = ""

# 공용 센티넬 상수 (메타데이터 로깅 및 데이터 정합성 유지)
# 백엔드 전반에서 추적용 메타데이터(meta payload)를 생성할 때, 식별자가 누락되었음을
# 일관되게 표현하기 위해 사용됩니다.
UNKNOWN_USER_ID: Final[str] = "anonymous"
UNKNOWN_FILE_ID: Final[str] = "unknown"
UNKNOWN_SNAPSHOT_ID: Final[str] = "unknown_snapshot"
