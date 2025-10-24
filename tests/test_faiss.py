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

from backend.chunking import chunk_with_metadata
from backend.embedding import get_embeddings, get_single_embedding
from backend.faiss_search import FAISSRetriever

def test_search_pipeline():
    """전체 검색 파이프라인 테스트"""
    
    print("=" * 50)
    print("FlowNote 검색 파이프라인 테스트")
    print("=" * 50)
    
    # 1. 샘플 문서
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
    
    # 2. 청킹
    print("\n" + "=" * 50)
    print("1. 청킹")
    print("=" * 50)
    
    chunks_meta = chunk_with_metadata(
        document,
        "test.md",
        chunk_size=200,
        chunk_overlap=50
    )
    
    print(f"✅ 청크 수: {len(chunks_meta)}")
    
    # 3. 임베딩
    print("\n" + "=" * 50)
    print("2. 임베딩")
    print("=" * 50)
    
    texts = [chunk['text'] for chunk in chunks_meta]
    embeddings, tokens, cost = get_embeddings(texts)
    
    print(f"✅ 임베딩 완료!")
    print(f"   - 토큰: {tokens}")
    print(f"   - 비용: ${cost:.6f}")
    
    # 4. FAISS 인덱스 생성
    print("\n" + "=" * 50)
    print("3. FAISS 인덱스")
    print("=" * 50)
    
    retriever = FAISSRetriever(dimension=1536)
    retriever.add_documents(texts, embeddings, chunks_meta)
    
    # 5. 검색 테스트
    print("\n" + "=" * 50)
    print("4. 검색 테스트")
    print("=" * 50)
    
    # 검색어
    query = "Python으로 어떻게 개발하나요?"
    print(f"\n검색어: {query}")
    
    # 검색어 임베딩
    query_embeddings, _, _ = get_embeddings([query], show_progress=False)
    query_embedding = query_embeddings[0]
    
    # 검색!
    results = retriever.search(query_embedding, top_k=3)
    
    print(f"\n검색 결과 ({len(results)}개):")
    for result in results:
        print(f"\n{result['rank']}위:")
        print(f"  - 유사도: {result['score']:.4f}")
        print(f"  - 파일: {result.get('filename', 'N/A')}")
        print(f"  - 텍스트: {result['text'][:100]}...")
    
    # 6. 통계
    print("\n" + "=" * 50)
    print("5. 통계")
    print("=" * 50)
    
    stats = retriever.get_stats()
    print(f"  - 총 문서: {stats['total_documents']}")
    print(f"  - 인덱스 크기: {stats['index_size']}")
    print(f"  - 벡터 차원: {stats['dimension']}")
    
    print("\n" + "=" * 50)
    print("🎉 모든 테스트 통과!")
    print("=" * 50)

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