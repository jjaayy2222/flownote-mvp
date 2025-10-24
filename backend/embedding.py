# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/embedding.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote 임베딩 관리
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from typing import List, Tuple
import numpy as np
from backend.config import get_embedding_client, EMBEDDING_MODEL

def get_embeddings(
    texts: List[str],
    show_progress: bool = True
) -> Tuple[List[List[float]], int, float]:
    """
    텍스트 리스트 → 임베딩 벡터 + 비용 계산
    
    Args:
        texts: 텍스트 리스트
        show_progress: 진행 상황 표시 여부
        
    Returns:
        Tuple[embeddings, tokens, cost]:
        - embeddings: 임베딩 벡터 리스트
        - tokens: 사용된 토큰 수
        - cost: 예상 비용 (USD)
        
    Example:
        >>> texts = ["안녕", "반가워"]
        >>> embeddings, tokens, cost = get_embeddings(texts)
        >>> print(f"토큰: {tokens}, 비용: ${cost:.6f}")
    """
    if not texts:
        return [], 0, 0.0
    
    try:
        # OpenAI Embedding API 호출
        client = get_embedding_client()
        
        if show_progress:
            print(f"📊 임베딩 생성 중... ({len(texts)}개 청크)")
        
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts
        )
        
        # 임베딩 추출
        embeddings = [item.embedding for item in response.data]
        
        # 토큰 & 비용 계산
        tokens = response.usage.total_tokens
        
        # Text-Embedding-3-Small: $0.00002/1k tokens
        cost_per_1k_tokens = 0.00002
        cost = (tokens / 1000) * cost_per_1k_tokens
        
        if show_progress:
            print(f"✅ 임베딩 완료!")
            print(f"   - 청크 수: {len(texts)}")
            print(f"   - 토큰 수: {tokens:,}")
            print(f"   - 예상 비용: ${cost:.6f}")
            print(f"   - 벡터 차원: {len(embeddings[0])}")
        
        return embeddings, tokens, cost
        
    except Exception as e:
        print(f"❌ 임베딩 생성 실패: {e}")
        return [], 0, 0.0


def get_single_embedding(text: str) -> List[float]:
    """
    단일 텍스트 → 임베딩 벡터
    (검색 쿼리용)
    
    Args:
        text: 검색 쿼리 텍스트
        
    Returns:
        List[float]: 임베딩 벡터
    """
    embeddings, _, _ = get_embeddings([text], show_progress=False)
    return embeddings[0] if embeddings else []


def calculate_similarity(
    embedding1: List[float],
    embedding2: List[float]
) -> float:
    """
    코사인 유사도 계산
    
    Args:
        embedding1: 첫 번째 임베딩
        embedding2: 두 번째 임베딩
        
    Returns:
        float: 유사도 (0~1, 1이 가장 유사)
        
    Example:
        >>> emb1 = [0.1, 0.2, 0.3]
        >>> emb2 = [0.1, 0.2, 0.3]
        >>> similarity = calculate_similarity(emb1, emb2)
        >>> print(f"유사도: {similarity:.4f}")
        1.0000
    """
    # numpy 배열로 변환
    vec1 = np.array(embedding1)
    vec2 = np.array(embedding2)
    
    # 코사인 유사도
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    similarity = dot_product / (norm1 * norm2)
    return float(similarity)


# 사용 예시 (테스트용)
if __name__ == "__main__":
    # 테스트 텍스트
    test_texts = [
        "FlowNote는 AI 대화 관리 도구입니다.",
        "키워드 검색으로 대화를 찾을 수 있습니다.",
        "Python으로 개발되었습니다."
    ]
    
    print("=" * 50)
    print("임베딩 테스트")
    print("=" * 50)
    
    # 임베딩 생성
    embeddings, tokens, cost = get_embeddings(test_texts)
    
    if embeddings:
        print(f"\n✅ 성공!")
        print(f"   - 임베딩 개수: {len(embeddings)}")
        print(f"   - 벡터 차원: {len(embeddings[0])}")
        print(f"   - 첫 5개 값: {embeddings[0][:5]}")
        
        # 유사도 계산
        print(f"\n유사도 계산:")
        sim = calculate_similarity(embeddings[0], embeddings[1])
        print(f"   - 청크 0 vs 청크 1: {sim:.4f}")


"""result

    ==================================================
    임베딩 테스트
    ==================================================
    📊 임베딩 생성 중... (3개 청크)
    ✅ 임베딩 완료!
        - 청크 수: 3
        - 토큰 수: 40
        - 예상 비용: $0.000001
        - 벡터 차원: 1536

    ✅ 성공!
        - 임베딩 개수: 3
        - 벡터 차원: 1536
        - 첫 5개 값: [-0.03015800751745701, 0.022111691534519196, -0.047065719962120056, -0.05024244636297226, -0.002251923317089677]

    유사도 계산:
        - 청크 0 vs 청크 1: 0.3841

"""