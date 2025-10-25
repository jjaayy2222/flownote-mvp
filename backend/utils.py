#━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/utils.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - 유틸리티 함수
"""

import tiktoken


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """
    텍스트의 토큰 수 계산
    
    Args:
        text: 토큰을 계산할 텍스트
        model: 사용할 모델 (기본: gpt-4)
        
    Returns:
        토큰 수
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        # 모델을 찾을 수 없으면 cl100k_base 사용
        encoding = tiktoken.get_encoding("cl100k_base")
    
    return len(encoding.encode(text))


def estimate_cost(tokens: int, cost_per_token: float) -> float:
    """
    토큰 수를 기반으로 비용 추정
    
    Args:
        tokens: 토큰 수
        cost_per_token: 토큰당 비용
        
    Returns:
        추정 비용 (USD)
    """
    return tokens * cost_per_token


def format_file_size(size_bytes: int) -> str:
    """
    파일 크기를 읽기 쉬운 형식으로 변환
    
    Args:
        size_bytes: 바이트 단위 크기
        
    Returns:
        포맷된 크기 (예: "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


if __name__ == "__main__":
    # 테스트
    test_text = "FlowNote는 AI 대화 관리 도구입니다."
    tokens = count_tokens(test_text)
    cost = estimate_cost(tokens, 0.02 / 1_000_000)
    
    print("=" * 50)
    print("유틸리티 함수 테스트")
    print("=" * 50)
    print(f"\n텍스트: {test_text}")
    print(f"토큰 수: {tokens}")
    print(f"예상 비용: ${cost:.6f}")
    print(f"파일 크기 예시: {format_file_size(1536)}")
    print("\n" + "=" * 50)


"""result_2

    ==================================================
    유틸리티 함수 테스트
    ==================================================

    텍스트: FlowNote는 AI 대화 관리 도구입니다.
    토큰 수: 13
    예상 비용: $0.000000
    파일 크기 예시: 1.5 KB

    ==================================================

"""