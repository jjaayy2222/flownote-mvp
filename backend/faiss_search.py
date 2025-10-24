# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/faiss_search.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote FAISS 검색 엔진
"""

import faiss
import numpy as np
from typing import List, Tuple, Dict

class FAISSRetriever:
    """
    FAISS 벡터 검색
    
    비유:
    도서관 색인 카드 시스템!
    """
    
    def __init__(self, dimension: int = 1536):
        """
        검색 엔진 초기화
        
        Args:
            dimension: 벡터 차원 (기본: 1536)
        """
        self.dimension = dimension
        self.index = faiss.IndexFlatL2(dimension)
        self.chunks = []           # 원본 텍스트 저장
        
    def add_documents(
        self,
        texts: List[str],
        embeddings: List[List[float]],
        meta: List[Dict] = None
    ):
        """
        문서 추가
        
        Args:
            texts: 텍스트 리스트
            embeddings: 임베딩 벡터 리스트
            meta 메타데이터 (선택)
        """
        # 벡터를 numpy 배열로 변환
        vectors = np.array(embeddings, dtype='float32')
        
        # FAISS 인덱스에 추가
        self.index.add(vectors)
        
        # 원본 텍스트 & 메타데이터 저장
        for i, text in enumerate(texts):
            chunk_data = {
                'text': text,
                'id': len(self.chunks)
            }
            if meta and i < len(meta):
                chunk_data.update(meta[i])
            
            self.chunks.append(chunk_data)
        
        print(f"✅ 문서 추가 완료!")
        print(f"   - 총 문서 수: {len(self.chunks)}")
        print(f"   - 인덱스 크기: {self.index.ntotal}")
    
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 3
    ) -> List[Dict]:
        """
        유사 문서 검색
        
        Args:
            query_embedding: 쿼리 임베딩
            top_k: 상위 몇 개 반환 (기본: 3)
            
        Returns:
            List[Dict]: 검색 결과 리스트
        """
        if self.index.ntotal == 0:
            print("❌ 인덱스가 비어있습니다!")
            return []
        
        # numpy 배열로 변환
        query_vector = np.array([query_embedding], dtype='float32')
        
        # FAISS 검색
        distances, indices = self.index.search(query_vector, top_k)
        
        # 결과 정리
        results = []
        for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
            if idx < len(self.chunks):
                result = {
                    'rank': i + 1,
                    'score': float(1 / (1 + dist)),         # 거리 → 유사도
                    'distance': float(dist),
                    **self.chunks[idx]
                }
                results.append(result)
        
        return results
    
    def get_stats(self) -> Dict:
        """
        통계 정보
        
        Returns:
            Dict: 통계 정보
        """
        return {
            'total_documents': len(self.chunks),
            'index_size': self.index.ntotal,
            'dimension': self.dimension
        }


# 사용 예시 (테스트용)
if __name__ == "__main__":
    print("=" * 50)
    print("FAISS 검색 테스트")
    print("=" * 50)
    
    # 1. 검색 엔진 초기화
    retriever = FAISSRetriever(dimension=1536)
    
    # 2. 샘플 데이터
    texts = [
        "FlowNote는 AI 대화 관리 도구입니다.",
        "Python으로 개발되었습니다.",
        "FAISS로 검색합니다."
    ]
    
    # 임베딩 (실제로는 OpenAI API 사용)
    # 여기서는 랜덤 벡터 사용
    embeddings = np.random.rand(3, 1536).tolist()
    
    # 3. 문서 추가
    retriever.add_documents(texts, embeddings)
    
    # 4. 검색
    query_embedding = np.random.rand(1536).tolist()
    results = retriever.search(query_embedding, top_k=2)
    
    print("\n검색 결과:")
    for result in results:
        print(f"\n{result['rank']}위:")
        print(f"  - 유사도: {result['score']:.4f}")
        print(f"  - 텍스트: {result['text']}")
    
    # 5. 통계
    stats = retriever.get_stats()
    print(f"\n통계:")
    print(f"  - 총 문서: {stats['total_documents']}")
    print(f"  - 인덱스 크기: {stats['index_size']}")



"""result

    ==================================================
    FAISS 검색 테스트
    ==================================================
    ✅ 문서 추가 완료!
        - 총 문서 수: 3
        - 인덱스 크기: 3

    검색 결과:

    1위:
        - 유사도: 0.0039
        - 텍스트: FlowNote는 AI 대화 관리 도구입니다.

    2위:
        - 유사도: 0.0038
        - 텍스트: Python으로 개발되었습니다.

    통계:
        - 총 문서: 3
        - 인덱스 크기: 3

"""