# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/faiss_search.py 
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - FAISS 검색
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import faiss
import numpy as np
from typing import List, Dict
from backend.embedding import EmbeddingGenerator


class FAISSRetriever:
    """FAISS 기반 벡터 검색"""
    
    def __init__(self, dimension: int = 1536):
        """
        Args:
            dimension: 임베딩 벡터 차원 (text-embedding-3-small: 1536)
        """
        self.dimension = dimension
        self.index = faiss.IndexFlatL2(dimension)
        self.documents = []
        self.embedding_generator = EmbeddingGenerator()
    
    def add_documents(self, documents: List[str], embeddings: List[List[float]]):
        """문서와 임베딩 추가"""
        if not documents or not embeddings:
            return
        
        if len(documents) != len(embeddings):
            raise ValueError("문서 수와 임베딩 수가 일치하지 않습니다!")
        
        # NumPy 배열로 변환
        embeddings_np = np.array(embeddings, dtype=np.float32)
        
        # FAISS 인덱스에 추가
        self.index.add(embeddings_np)
        
        # 문서 저장
        self.documents.extend(documents)
    
    def search(self, query: str, k: int = 3) -> List[Dict]:
        """쿼리에 가장 유사한 문서 검색"""
        if self.index.ntotal == 0:
            return []
        
        # 쿼리 임베딩 생성
        query_result = self.embedding_generator.generate_embeddings([query])
        query_embedding = np.array([query_result['embeddings'][0]], dtype=np.float32)
        
        # 검색
        distances, indices = self.index.search(query_embedding, min(k, self.index.ntotal))
        
        # 결과 반환
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < len(self.documents):
                results.append({
                    "text": self.documents[idx],
                    "distance": float(dist),
                    "similarity": 1 / (1 + float(dist))
                })
        
        return results
    
    def clear(self):
        """인덱스 초기화"""
        self.index = faiss.IndexFlatL2(self.dimension)
        self.documents = []
    
    def size(self) -> int:
        """인덱스에 저장된 문서 수"""
        return self.index.ntotal


if __name__ == "__main__":
    print("=" * 50)
    print("FAISS 검색 테스트")
    print("=" * 50)
    
    # 1. Retriever 초기화
    retriever = FAISSRetriever()
    
    # 2. 테스트 문서
    docs = [
        "FlowNote는 AI 대화 관리 도구입니다.",
        "대화 내용을 검색하고 분석할 수 있습니다.",
        "마크다운으로 대화를 내보낼 수 있습니다."
    ]
    
    # 3. 임베딩 생성
    embedding_generator = EmbeddingGenerator()
    result = embedding_generator.generate_embeddings(docs)
    embeddings = result['embeddings']  # ✅ 실제 임베딩 벡터 리스트!
    
    # 4. 문서 추가
    retriever.add_documents(docs, embeddings)
    print(f"✅ 문서 추가 완료!")
    print(f"   - 총 문서 수: {len(docs)}")
    print(f"   - 인덱스 크기: {retriever.size()}")
    
    # 5. 검색
    query = "대화를 어떻게 관리하나요?"
    results = retriever.search(query, k=2)
    
    print(f"\n검색 결과:\n")
    for i, result in enumerate(results, 1):
        print(f"{i}위:")
        print(f"  - 유사도: {result['similarity']:.4f}")
        print(f"  - 텍스트: {result['text']}")
        print()
    
    print("=" * 50)



"""result_3

    ==================================================
    FAISS 검색 테스트
    ==================================================

    ✅ 문서 추가 완료!
        - 총 문서 수: 3
        - 인덱스 크기: 3

    검색 결과:

    1위:
        - 유사도: 0.5385
        - 텍스트: 대화 내용을 검색하고 분석할 수 있습니다.

    2위:
        - 유사도: 0.4233
        - 텍스트: 마크다운으로 대화를 내보낼 수 있습니다.

    ==================================================

"""