# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# tests/test_chunking_embedding.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
청킹 & 임베딩 통합 테스트
"""

import sys
from pathlib import Path

# 프로젝트 루트 추가 (상위 폴더)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.chunking import chunk_text, chunk_with_metadata
from backend.embedding import get_embeddings
from backend.utils import read_file

def test_full_pipeline():
    """전체 파이프라인 테스트"""
    
    print("=" * 50)
    print("FlowNote 청킹 & 임베딩 테스트")
    print("=" * 50)
    
    # 1. 샘플 텍스트
    sample_text = """
    FlowNote MVP 프로젝트입니다.
    
    이 도구는 AI 대화를 체계적으로 저장하고 검색합니다.
    사용자는 Markdown 파일을 업로드하고,
    키워드로 검색하여 필요한 정보를 찾을 수 있습니다.
    
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
    """ * 3
    
    # 2. 청킹
    print("\n" + "=" * 50)
    print("1. 청킹 테스트")
    print("=" * 50)
    
    chunks = chunk_text(
        sample_text,
        chunk_size=200,
        chunk_overlap=50
    )
    
    print(f"✅ 청크 수: {len(chunks)}")
    print(f"✅ 첫 번째 청크 길이: {len(chunks[0])}")
    print(f"\n첫 번째 청크 미리보기:")
    print(f"{chunks[0][:100]}...")
    
    # 3. 메타데이터 포함 청킹
    print("\n" + "=" * 50)
    print("2. 메타데이터 청킹")
    print("=" * 50)
    
    chunks_meta = chunk_with_metadata(
        sample_text,
        "test.md",
        chunk_size=200,
        chunk_overlap=50
    )
    
    print(f"✅ 청크 수: {len(chunks_meta)}")
    print(f"\n첫 번째 청크 메타데이터:")
    print(f"  - filename: {chunks_meta[0]['filename']}")
    print(f"  - chunk_id: {chunks_meta[0]['chunk_id']}")
    print(f"  - start_pos: {chunks_meta[0]['start_pos']}")
    print(f"  - end_pos: {chunks_meta[0]['end_pos']}")
    
    # 4. 임베딩
    print("\n" + "=" * 50)
    print("3. 임베딩 테스트")
    print("=" * 50)
    
    # 처음 3개만 테스트 (비용 절약)
    test_chunks = [chunk['text'] for chunk in chunks_meta[:3]]
    
    embeddings, tokens, cost = get_embeddings(test_chunks)
    
    if embeddings:
        print(f"\n✅ 임베딩 성공!")
        print(f"  - 임베딩 개수: {len(embeddings)}")
        print(f"  - 벡터 차원: {len(embeddings[0])}")
        print(f"  - 총 토큰: {tokens:,}")
        print(f"  - 총 비용: ${cost:.6f}")
        
        # 5. 비용 예측
        print("\n" + "=" * 50)
        print("4. 전체 파일 비용 예측")
        print("=" * 50)
        
        total_chunks = len(chunks_meta)
        estimated_tokens = tokens * (total_chunks / 3)
        estimated_cost = cost * (total_chunks / 3)
        
        print(f"  - 전체 청크 수: {total_chunks}")
        print(f"  - 예상 토큰: {estimated_tokens:,.0f}")
        print(f"  - 예상 비용: ${estimated_cost:.6f}")
        
        # 6. 결과 요약
        print("\n" + "=" * 50)
        print("5. 테스트 결과 요약")
        print("=" * 50)
        
        print(f"✅ 청킹: 성공 ({total_chunks}개 청크)")
        print(f"✅ 임베딩: 성공 ({len(embeddings)}개 테스트)")
        print(f"✅ 비용 계산: 성공")
        print(f"\n🎉 모든 테스트 통과!")
    
    else:
        print("❌ 임베딩 실패")

if __name__ == "__main__":
    test_full_pipeline()



"""result

    ==================================================
    FlowNote 청킹 & 임베딩 테스트
    ==================================================

    ==================================================
    1. 청킹 테스트
    ==================================================
    ✅ 청크 수: 6
    ✅ 첫 번째 청크 길이: 200

    첫 번째 청크 미리보기:

        FlowNote MVP 프로젝트입니다.
        
        이 도구는 AI 대화를 체계적으로 저장하고 검색합니다.
        사용자는 Markdown 파일을 업로드하고,
        ...

    ==================================================
    2. 메타데이터 청킹
    ==================================================
    ✅ 청크 수: 6

    첫 번째 청크 메타데이터:
        - filename: test.md
        - chunk_id: 0
        - start_pos: 0
        - end_pos: 200

    ==================================================
    3. 임베딩 테스트
    ==================================================
    📊 임베딩 생성 중... (3개 청크)
    ✅ 임베딩 완료!
        - 청크 수: 3
        - 토큰 수: 353
        - 예상 비용: $0.000007
        - 벡터 차원: 1536

    ✅ 임베딩 성공!
        - 임베딩 개수: 3
        - 벡터 차원: 1536
        - 총 토큰: 353
        - 총 비용: $0.000007

    ==================================================
    4. 전체 파일 비용 예측
    ==================================================
        - 전체 청크 수: 6
        - 예상 토큰: 706
        - 예상 비용: $0.000014

    ==================================================
    5. 테스트 결과 요약
    ==================================================
    ✅ 청킹: 성공 (6개 청크)
    ✅ 임베딩: 성공 (3개 테스트)
    ✅ 비용 계산: 성공

    🎉 모든 테스트 통과!

"""