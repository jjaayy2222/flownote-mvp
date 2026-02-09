# backend/services/diff_service.py

import difflib
from typing import Dict, Any


def generate_diff(local_content: str, remote_content: str) -> Dict[str, Any]:
    """
    두 텍스트 간의 Diff(차이점)를 생성합니다.

    Args:
        local_content (str): 로컬 파일 내용
        remote_content (str): 리모트 파일 내용

    Returns:
        dict: 다음 키를 포함하는 딕셔너리
            - unified (str): Unified format diff string
            - html (str): Side-by-side HTML diff table
            - stats (dict): {'additions': int, 'deletions': int}
    """
    # 텍스트를 줄 단위로 분리 (개행 문자 유지 - Unified 용)
    local_lines_unified = local_content.splitlines(keepends=True)
    remote_lines_unified = remote_content.splitlines(keepends=True)

    # 텍스트를 줄 단위로 분리 (개행 문자 제거 - HTML 용)
    # Side-by-Side 테이블에서 불필요한 줄바꿈 방지
    local_lines_html = local_content.splitlines()
    remote_lines_html = remote_content.splitlines()

    # 1. Unified Diff 생성
    # fromfile='Local', tofile='Remote'로 명시
    unified_diff_gen = difflib.unified_diff(
        local_lines_unified, remote_lines_unified, fromfile="Local", tofile="Remote"
    )
    unified_diff_list = list(unified_diff_gen)
    unified_diff_str = "".join(unified_diff_list)

    # 2. HTML Diff (Side-by-Side) 생성
    html_diff = difflib.HtmlDiff().make_table(
        local_lines_html,
        remote_lines_html,
        fromdesc="Local",
        todesc="Remote",
        context=True,  # 변경된 부분 주변만 표시 (False면 전체 파일)
        numlines=5,  # 컨텍스트 라인 수
    )

    # 3. 통계 계산 (Unified Diff 기반)
    # Unified Diff 헤더(---, +++, @@)를 제외하고 실제 변경사항만 카운트
    # +로 시작하면 addition, -로 시작하면 deletion
    additions = 0
    deletions = 0

    for line in unified_diff_list:
        # 헤더 라인은 건너뜀
        if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
            continue

        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1

    return {
        "unified": unified_diff_str,
        "html": html_diff,
        "stats": {"additions": additions, "deletions": deletions},
    }
