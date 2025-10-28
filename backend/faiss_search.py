# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/faiss_search.py (수정)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
from typing import List, Dict, Union
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
        self.documents = []                         # dict 객체 저장
        self.embedding_generator = EmbeddingGenerator()
    
    def add_documents(
        self, 
        embeddings: np.ndarray,         # 순서 변경
        documents: List[Dict]           # Dict 타입으로 변경
    ):
        """
        문서와 임베딩 추가
        
        Args:
            embeddings: 임베딩 벡터 배열
            documents: 문서 dict 리스트 (content, metadata 포함)
        """
        if not documents or embeddings is None:
            return
        
        if len(documents) != len(embeddings):
            raise ValueError(f"문서 수({len(documents)})와 임베딩 수({len(embeddings)})가 일치하지 않습니다!")
        
        # NumPy 배열로 변환
        if not isinstance(embeddings, np.ndarray):
            embeddings_np = np.array(embeddings, dtype=np.float32)
        else:
            embeddings_np = embeddings.astype(np.float32)
        
        # FAISS 인덱스에 추가
        self.index.add(embeddings_np)
        
        # 문서 dict 그대로 저장
        self.documents.extend(documents)
        print(f"✅ FAISS에 {len(documents)}개 문서 추가 완료")
    
    def search(self, query: str, k: int = 3) -> List[Dict]:
        """
        쿼리에 가장 유사한 문서 검색
        
        Args:
            query: 검색 쿼리
            k: 반환할 결과 수
            
        Returns:
            검색 결과 리스트 (content, metadata, score 포함)
        """
        if self.index.ntotal == 0:
            return []
        
        # 쿼리 임베딩 생성
        result = self.embedding_generator.generate_embeddings([query])
        query_embedding = result["embeddings"][0]       # dict에서 첫 번째 임베딩 추출
        
        # NumPy 배열로 변환 (FAISS가 기대하는 형태: (1, 1536))
        query_vector = np.array([query_embedding], dtype=np.float32)
    
        # 검색
        distances, indices = self.index.search(query_vector, min(k, self.index.ntotal))
        
        # 결과 반환 (dict 구조 유지)
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < len(self.documents):
                doc = self.documents[idx]
                
                # 유사도 계산 (거리 → 유사도)
                similarity = 1 / (1 + float(dist))
                
                results.append({
                    "content": doc["content"],              # content 키 사용
                    "metadata": doc["metadata"],            # metadata 유지
                    "score": similarity,                    # score로 통일
                    "distance": float(dist)
                })
        
        return results
    
    def clear(self):
        """인덱스 초기화"""
        self.index = faiss.IndexFlatL2(self.dimension)
        self.documents = []
    
    def size(self) -> int:
        """인덱스에 저장된 문서 수"""
        return self.index.ntotal


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 테스트 코드 (수정 버전)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    print("=" * 50)
    print("FAISS 검색 테스트")
    print("=" * 50)
    
    # 1. Retriever 초기화
    retriever = FAISSRetriever()
    
    # 2. 테스트 문서 (dict 구조)
    docs = [
        {
            "content": "FlowNote는 AI 대화 관리 도구입니다.",
            "metadata": {"source": "test.txt", "chunk_index": 0}
        },
        {
            "content": "대화 내용을 검색하고 분석할 수 있습니다.",
            "metadata": {"source": "test.txt", "chunk_index": 1}
        },
        {
            "content": "마크다운으로 대화를 내보낼 수 있습니다.",
            "metadata": {"source": "test.txt", "chunk_index": 2}
        }
    ]
    
    # 3. 임베딩 생성
    embedding_generator = EmbeddingGenerator()
    texts = [doc["content"] for doc in docs]
    
    # ✅ 수정: result에서 embeddings 추출!
    result = embedding_generator.generate_embeddings(texts)
    embeddings = result["embeddings"]                   # 추가
    
    print(f"\n✅ 임베딩 생성 완료:")
    print(f" - 청크 수: {len(embeddings)}")
    print(f" - 토큰 수: {result['tokens']}")
    print(f" - 예상 비용: ${result['cost']:.6f}")
    print(f" - 벡터 차원: {len(embeddings[0])}")
    
    # 4. NumPy 배열로 변환 (FAISS가 기대하는 형태)
    embeddings_np = np.array(embeddings, dtype=np.float32)
    
    # 5. 문서 추가
    retriever.add_documents(embeddings_np, docs)
    print(f"\n✅ FAISS 인덱스 추가 완료")
    print(f"    - 총 문서 수: {len(docs)}")
    print(f"    - 인덱스 크기: {retriever.size()}")
    
    # 6. 검색
    query = "대화를 어떻게 관리하나요?"
    print(f"\n🔍 검색 쿼리: '{query}'")
    results = retriever.search(query, k=2)
    
    print(f"\n검색 결과 ({len(results)}개):")
    print("-" * 50)
    for i, result in enumerate(results, 1):
        print(f"\n{i}위:")
        print(f"    - 유사도: {result['score']:.4f}")
        print(f"    - 내용: {result['content']}")
        print(f"    - 출처: {result['metadata']['source']}")
    
    print("\n" + "=" * 50)




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


"""result_4

    ==================================================
    FAISS 검색 테스트
    ==================================================

    ✅ 임베딩 생성 완료:
        - 청크 수: 3
        - 토큰 수: 48
        - 예상 비용: $0.000001
        - 벡터 차원: 1536
    ✅ FAISS에 3개 문서 추가 완료

    ✅ FAISS 인덱스 추가 완료
        - 총 문서 수: 3
        - 인덱스 크기: 3

    🔍 검색 쿼리: '대화를 어떻게 관리하나요?'

    검색 결과 (2개):
    --------------------------------------------------

    1위:
        - 유사도: 1.0000
        - 내용: FlowNote는 AI 대화 관리 도구입니다.
        - 출처: test.txt

    2위:
        - 유사도: 0.4368
        - 내용: 마크다운으로 대화를 내보낼 수 있습니다.
        - 출처: test.txt

    ==================================================

"""

"""result_5

    ==================================================
    FAISS 검색 테스트
    ==================================================

    ✅ 임베딩 생성 완료:
        - 청크 수: 3
        - 토큰 수: 48
        - 예상 비용: $0.000001
        - 벡터 차원: 1536
    ✅ FAISS에 3개 문서 추가 완료

    ✅ FAISS 인덱스 추가 완료
        - 총 문서 수: 3
        - 인덱스 크기: 3

    🔍 검색 쿼리: '대화를 어떻게 관리하나요?'

    검색 결과 (2개):
    --------------------------------------------------

    1위:
        - 유사도: 0.5387
        - 내용: 대화 내용을 검색하고 분석할 수 있습니다.
        - 출처: test.txt

    2위:
        - 유사도: 0.4233
        - 내용: 마크다운으로 대화를 내보낼 수 있습니다.
        - 출처: test.txt

    ==================================================

"""