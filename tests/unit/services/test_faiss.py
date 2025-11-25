# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# tests/test_faiss.py 
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FAISS 검색 통합 테스트
"""

import sys
from pathlib import Path

# 프로젝트 루트 추가 (상위 폴더)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import numpy as np
from typing import List, Dict, Any
import json
import re

from backend.chunking import TextChunker
from backend.embedding import EmbeddingGenerator
from backend.faiss_search import FAISSRetriever
from backend.utils import count_tokens, estimate_cost

def test_search_pipeline():
    """전체 검색 파이프라인 테스트"""
    
    # 1. Retriever 초기화
    retriever = FAISSRetriever()
    
    print("=" * 50)
    print("FlowNote 검색 파이프라인 테스트")
    print("=" * 50)
    
    # 2. 샘플 문서
    document = """
    FlowNote는 AI 대화를 체계적으로 저장하고 검색하는 도구입니다.
    사용자는 Markdown 파일을 업로드하고 키워드로 검색할 수 있습니다.
    
    주요 기능:
    1. 파일 업로드
    2. 자동 청킹
    3. 벡터 임베딩
    4. FAISS 검색
    5. 결과 요약
    
    기술 스택:
    - Python 3.11
    - Streamlit
    - OpenAI API
    - FAISS
    """ * 2
    
    # 3. 청킹
    print("\n" + "=" * 50)
    print("1. 청킹")
    print("=" * 50)
    
    chunker= TextChunker(chunk_size=200, chunk_overlap=50)
    
    chunks= chunker.chunk_text(document)

    print(f"✅ 청크 수: {len(chunks)}")
    print(f"✅ 첫 번째 청크 길이: {len(chunks[0])}")
    print(f"\n첫 번째 청크 미리보기:")
    print(f"{chunks[0][:100]}...")
    
    # 청크 결과 = 문서로 변환하기
    chunk_results: List[Dict[str, Any]] = []

    # 딕셔너리 생성 반복문: 'content', 'metadata', 'chunk_id' 키를 포함
    for i, chunk_content in enumerate(chunks):
        # 💥 FAISS 검색기(faiss_search.py)가 기대하는 구조로 생성하기
        chunk_dict = {
            "chunk_id": i,
            "content": chunk_content, # Key Error 해결 1: 'content' 키 사용
            "metadata": {}            # Key Error 해결 2: 'metadata' 키 (빈 딕셔너리) 추가
        }
        chunk_results.append(chunk_dict)
    
    # 3. 결과 출력 (확인용)
    print("=" * 50)
    print(f"✅ 총 {len(chunk_results)}개의 청크 딕셔너리가 생성되었습니다.")
    print("=" * 50)
    
    if chunk_results:
        print("반복문으로 생성된 전체 딕셔너리 리스트 (FAISS 구조 통일):")
        # json.dumps를 사용하여 딕셔너리 구조를 보기 좋게 출력
        print(json.dumps(chunk_results, indent=4, ensure_ascii=False))

    print("=" * 50)
    print("🎉 FAISS 검색기 요구 사항에 맞게 구조가 통일되었습니다.")
    
    # 3. 결과 출력 (확인용)
    print("=" * 50)
    print(f"✅ 총 {len(chunk_results)}개의 단순 청크 딕셔너리가 생성되었습니다.")
    print("=" * 50)
    
    if chunk_results:
        print("반복문으로 생성된 전체 딕셔너리 리스트 (단순 구조):")
        # json.dumps를 사용하여 딕셔너리 구조를 보기 좋게 출력
        print(json.dumps(chunk_results, indent=4, ensure_ascii=False))

    print("=" * 50)
    print("🎉 단순 구조의 딕셔너리 리스트로 확인 가능")
    
    
    documents = chunk_results    
    
    # 4. 임베딩
    print("\n" + "=" * 50)
    print("2. 임베딩")
    print("=" * 50)
    
    embedding_generator = EmbeddingGenerator()
    
    texts = [chunk[1] for chunk in chunks]
    #embeddings, tokens, cost = generator.generate_embeddings(texts)
    
    result = embedding_generator.generate_embeddings(texts)
    embeddings = result["embeddings"] 
    
    if result['embeddings']:
        print(f"\n✅ 임베딩 성공!")
        print(f"  - 임베딩 개수: {len(result['embeddings'])}")
        print(f"  - 벡터 차원: {len(result['embeddings'][0])}")
        print(f"  - 청크 수: {len(embeddings)}")
        print(f"  - 토큰 수: {result['tokens']}")
        print(f"  - 예상 비용: ${result['cost']:.6f}")
    else:
        print("❌ 임베딩 실패")
    
    # 5. FAISS 인덱스 생성
    print("\n" + "=" * 50)
    print("3. FAISS 인덱스")
    print("=" * 50)
    
    # NumPy 배열로 변환 (FAISS가 기대하는 형태)
    embeddings_np = np.array(result['embeddings'], dtype=np.float32)
    
    # 6. 문서 추가
    retriever.add_documents(embeddings_np, documents)
    
    print(f"\n✅ FAISS 인덱스 추가 완료")
    print(f"    - 총 문서 수: {len(documents)}")
    print(f"    - 인덱스 크기: {retriever.size()}")
    
    # 6. 검색 테스트
    print("\n" + "=" * 50)
    print("4. 검색 테스트")
    print("=" * 50)
    
    # 검색어
    query = "Python으로 어떻게 개발하나요?"
    print(f"\n검색어: {query}")
    
    # 쿼리 검색
    results = retriever.search(query, k=2)
    
    print(f"\n검색 결과 ({len(results)}개):")
    print("-" * 50)
    for i, result in enumerate(results, 1):
        print(f"\n{i}위:")
        print(f"    - 유사도: {result['score']:.4f}")
        print(f"    - 내용: {result['content']}")
        print(f"    - 출처: {result['metadata']}")
    
    print("\n" + "=" * 50)


if __name__ == "__main__":
    test_search_pipeline()



"""result

    ==================================================
    FlowNote 검색 파이프라인 테스트
    ==================================================

    ==================================================
    1. 청킹
    ==================================================
    ✅ 청크 수: 4

    ==================================================
    2. 임베딩
    ==================================================
    📊 임베딩 생성 중... (4개 청크)
    ✅ 임베딩 완료!
        - 청크 수: 4
        - 토큰 수: 367
        - 예상 비용: $0.000007
        - 벡터 차원: 1536
    ✅ 임베딩 완료!
        - 토큰: 367
        - 비용: $0.000007

    ==================================================
    3. FAISS 인덱스
    ==================================================
    ✅ 문서 추가 완료!
        - 총 문서 수: 4
        - 인덱스 크기: 4

    ==================================================
    4. 검색 테스트
    ==================================================

    검색어: Python으로 어떻게 개발하나요?

    검색 결과 (3개):

    1위:
        - 유사도: 0.4065
        - 파일: test.md
        - 텍스트: 
            - Python 3.11
            - Streamlit
            - OpenAI API
            - FAISS
            ...

    2위:
    - 유사도: 0.3951
    - 파일: test.md
    - 텍스트:  4. FAISS 검색
        5. 결과 요약
        
        기술 스택:
        - Python 3.11
        - Streamlit
        - OpenAI API
        - F...

    3위:
    - 유사도: 0.3902
    - 파일: test.md
    - 텍스트: 니다.
        사용자는 Markdown 파일을 업로드하고 키워드로 검색할 수 있습니다.
        
        주요 기능:
        1. 파일 업로드
        2. 자동 청킹
        3. 벡...

    ==================================================
    5. 통계
    ==================================================
    - 총 문서: 4
    - 인덱스 크기: 4
    - 벡터 차원: 1536

    ==================================================
    🎉 모든 테스트 통과!
    ==================================================

"""