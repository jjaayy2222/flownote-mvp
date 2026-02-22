# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/bm25_search.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - BM25 희소 벡터(키워드) 검색
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from typing import List, Dict, Optional
from rank_bm25 import BM25Okapi

class BM25Retriever:
    """BM25 (Rank BM25) 기반 희소 벡터(키워드) 검색"""
    
    def __init__(self):
        self.bm25: Optional[BM25Okapi] = None
        self.documents: List[Dict] = []
        
    def _tokenize(self, text: str) -> List[str]:
        """간단한 띄어쓰기 기반 토크나이징"""
        # 영문의 경우 소문자화하여 검색 품질을 높임
        return text.lower().split()
        
    def add_documents(self, documents: List[Dict]):
        """
        문서 추가 및 BM25 인덱스 빌드
        
        Args:
            documents: 문서 dict 리스트 (content, metadata 포함)
        """
        if not documents:
            return
            
        self.documents.extend(documents)
        
        # rank_bm25는 점진적 추가가 아닌 전체 데이터 코퍼스를 한 번에 빌드해야 함
        corpus = [self._tokenize(doc["content"]) for doc in self.documents]
        self.bm25 = BM25Okapi(corpus)
        print(f"✅ BM25 인덱스 빌드 완료 (총 {len(self.documents)}개 문서)")

    def search(self, query: str, k: int = 3) -> List[Dict]:
        """
        쿼리에 가장 유사한 문서 검색
        
        Args:
            query: 검색 쿼리
            k: 반환할 결과 수
            
        Returns:
            검색 결과 리스트 (content, metadata, score 포함)
        """
        if not self.bm25 or not self.documents:
            return []
            
        tokenized_query = self._tokenize(query)
        doc_scores = self.bm25.get_scores(tokenized_query)
        
        # 높은 점수 순으로 정렬
        top_k_indices = sorted(range(len(doc_scores)), key=lambda i: doc_scores[i], reverse=True)[:k]
        
        results = []
        for idx in top_k_indices:
            score = doc_scores[idx]
            if score > 0: # 점수가 0보다 큰(연관성 있는) 문서만 반환
                doc = self.documents[idx]
                results.append({
                    "content": doc["content"],
                    "metadata": doc["metadata"],
                    "score": float(score),
                    "distance": 0.0 # BM25는 distance 개념 대신 score를 사용
                })
                
        return results
        
    def clear(self):
        """인덱스 초기화"""
        self.bm25 = None
        self.documents = []
        
    def size(self) -> int:
        """인덱스에 저장된 문서 수"""
        return len(self.documents)

if __name__ == "__main__":
    print("=" * 50)
    print("BM25 검색 테스트")
    print("=" * 50)
    
    retriever = BM25Retriever()
    
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
    
    retriever.add_documents(docs)
    
    query = "대화를 어떻게 관리하나요"
    print(f"\n🔍 검색 쿼리: '{query}'")
    results = retriever.search(query, k=2)
    
    print(f"\n검색 결과 ({len(results)}개):")
    print("-" * 50)
    for i, result in enumerate(results, 1):
        print(f"\n{i}위:")
        print(f"    - 점수: {result['score']:.4f}")
        print(f"    - 내용: {result['content']}")
        print(f"    - 출처: {result['metadata']['source']}")
    
    print("\n" + "=" * 50)
