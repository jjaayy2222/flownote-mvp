# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/embedding.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - 임베딩 생성
"""

from backend.config import get_embedding_model, EMBEDDING_MODEL, EMBEDDING_COSTS
from backend.utils import count_tokens, estimate_cost


class EmbeddingGenerator:
    """임베딩 생성 클래스"""
    
    def __init__(self, model_name: str = EMBEDDING_MODEL):
        self.model_name = model_name
        self.client = get_embedding_model(model_name)
        self.cost_per_token = EMBEDDING_COSTS.get(model_name.split('/')[-1], 0.02 / 1_000_000)
    
    def generate_embeddings(self, texts: list[str]) -> dict:
        """텍스트 리스트에 대한 임베딩 생성"""
        if not texts:
            return {"embeddings": [], "tokens": 0, "cost": 0.0}
        
        # 토큰 수 계산
        total_tokens = sum(count_tokens(text) for text in texts)
        estimated_cost = estimate_cost(total_tokens, self.cost_per_token)
        
        # 임베딩 생성
        response = self.client.embeddings.create(
            model=self.model_name,
            input=texts
        )
        
        embeddings = [item.embedding for item in response.data]
        
        return {
            "embeddings": embeddings,
            "tokens": total_tokens,
            "cost": estimated_cost
        }


if __name__ == "__main__":
    generator = EmbeddingGenerator()
    
    test_texts = [
        "FlowNote는 AI 대화 관리 도구입니다.",
        "대화 내용을 검색하고 분석할 수 있습니다.",
        "마크다운으로 대화를 내보낼 수 있습니다."
    ]
    
    print("=" * 50)
    print("임베딩 테스트")
    print("=" * 50)
    print(f"\n📊 임베딩 생성 중... ({len(test_texts)}개 청크)")
    
    result = generator.generate_embeddings(test_texts)
    
    print(f"✅ 임베딩 완료!")
    print(f"   - 청크 수: {len(result['embeddings'])}")
    print(f"   - 토큰 수: {result['tokens']}")
    print(f"   - 예상 비용: ${result['cost']:.6f}")
    print(f"   - 벡터 차원: {len(result['embeddings'][0])}")
    
    print("\n" + "=" * 50)



"""result_2

    - 실행 방법_1: 프로젝트 루트에서 실행 시
        python -m backend.embedding
    
    - 실행 방법_2:
        python -m backend.faiss_search

    ==================================================
    임베딩 테스트
    ==================================================

    📊 임베딩 생성 중... (3개 청크)
    ✅ 임베딩 완료!
        - 청크 수: 3
        - 토큰 수: 48
        - 예상 비용: $0.000001
        - 벡터 차원: 1536

    ==================================================

"""



"""result_3

    ==================================================
    임베딩 테스트
    ==================================================

    📊 임베딩 생성 중... (3개 청크)
    ✅ 임베딩 완료!
        - 청크 수: 3
        - 토큰 수: 48
        - 예상 비용: $0.000001
        - 벡터 차원: 1536

    ==================================================

"""