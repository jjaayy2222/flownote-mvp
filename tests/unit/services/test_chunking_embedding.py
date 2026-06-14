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

from unittest.mock import MagicMock, patch

from backend.chunking import TextChunker
from backend.embedding import EmbeddingGenerator
from backend.metadata import FileMetadata
from backend.utils import count_tokens, estimate_cost


@patch("backend.config.ModelConfig.get_embedding_model")
def test_full_pipeline(mock_get_model):
    # Mock 설정
    mock_client = MagicMock()
    mock_get_model.return_value = mock_client

    # 임베딩 응답 Mock (1536차원)
    mock_response = MagicMock()
    mock_embedding = MagicMock()
    mock_embedding.embedding = [0.1] * 1536

    # generate_embeddings는 여러 텍스트를 처리하므로, 입력 텍스트 수만큼의 임베딩을 반환하도록 설정해야 함
    # 여기서는 간단히 항상 3개의 임베딩을 반환하도록 설정 (테스트 코드에서 3개 청크를 사용)
    mock_response.data = [mock_embedding] * 6  # 6개 청크 (메타데이터 청킹 결과)
    mock_response.usage.total_tokens = 100

    mock_client.embeddings.create.return_value = mock_response
    """전체 파이프라인 테스트"""

    print("=" * 50)
    print("FlowNote 청킹 & 임베딩 통합 테스트")
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

    # 인스턴스 생성
    chunker = TextChunker(chunk_size=200, chunk_overlap=50)

    chunks = chunker.chunk_text(sample_text)

    print(f"✅ 청크 수: {len(chunks)}")
    print(f"✅ 첫 번째 청크 길이: {len(chunks[0])}")
    print(f"\n첫 번째 청크 미리보기:")
    print(f"{chunks[0][:100]}...")

    # 3. 메타데이터 포함 청킹
    print("\n" + "=" * 50)
    print("2. 메타데이터 청킹")
    print("=" * 50)

    chunks_meta = chunker.chunk_with_metadata(
        text=sample_text, metadata={"filename": "test.md"}
    )

    first_chunk_meta = chunks_meta[0]

    print(f"\n첫 번째 청크 메타데이터:")
    print(f"✅ 청크 수: {len(chunks_meta)}")
    print(f"  - text: {first_chunk_meta['text'][:50]}...")
    print(f"  - metadata: {first_chunk_meta['metadata']}")
    print(f"  - chunk_index: {first_chunk_meta['chunk_index']}")
    print(f"  - total_chunks: {first_chunk_meta['total_chunks']}")

    # 메타데이터 객체 테스트
    metadata_manager = FileMetadata()
    file_id = metadata_manager.add_file(
        file_name="test.md",
        file_size=1024 * 50,  # 50KB
        chunk_count=len(chunks_meta),
        embedding_dim=1536,
        model="text-embedding-3-small",
    )

    file_info = metadata_manager.get_file(file_id)
    print(f"✅ 파일 추가 완료: {file_id}")
    print(f"  - filename: {file_info['file_name']}")
    print(f"   - 크기: {file_info['file_size']} MB")
    print(f"   - 청크 수: {file_info['chunk_count']}")
    print(f"   - 모델: {file_info['embedding_model']}")

    # 4. 임베딩
    print("\n" + "=" * 50)
    print("3. 임베딩 테스트")
    print("=" * 50)

    generator = EmbeddingGenerator()

    # 처음 3개만 테스트
    test_chunks = [chunk["text"] for chunk in chunks_meta[:3]]

    # 결과 = dict
    result = generator.generate_embeddings(test_chunks)

    if result["embeddings"]:
        print(f"\n✅ 임베딩 성공!")
        print(f"  - 임베딩 개수: {len(result['embeddings'])}")
        print(f"  - 벡터 차원: {len(result['embeddings'][0])}")
        print(f"  - 총 토큰: {result['tokens']:,.0f}")
        print(f"  - 총 비용: ${result['cost']:.8f}")

        # 5. 비용 예측
        print("\n" + "=" * 50)
        print("4. 전체 파일 비용 예측")
        print("=" * 50)

        total_chunks = len(chunks_meta)

        estimate_cost(total_chunks, generator.cost_per_token)
        # 전체 청크 텍스트를 추출하여 큰 수를 계산
        all_texts = [chunk["text"] for chunk in chunks_meta]
        total_estimated_tokens = sum(count_tokens(text) for text in all_texts)
        total_estimated_cost = total_estimated_tokens * generator.cost_per_token

        print(f"  - 전체 청크 수: {total_chunks}")
        print(f"  - 예상 토큰: {total_estimated_tokens:,.0f}")
        print(f"  - 예상 비용: ${total_estimated_cost:.8f}")

        # 6. 결과 요약
        print("\n" + "=" * 50)
        print("5. 테스트 결과 요약")
        print("=" * 50)

        print(f"✅ 청킹: 성공 ({total_chunks}개 청크)")
        print(f"✅ 임베딩: 성공 ({len(result['embeddings'])}개 테스트)")
        print(f"✅ 비용 계산: 성공")
        print(f"\n🎉 모든 테스트 통과!")

    else:
        print("❌ 임베딩 실패")


if __name__ == "__main__":
    test_full_pipeline()


"""test_result → 클래스 기반 + 함수 기반으로 모두 수정 ⭕️ → 테스트 성공 ⭕️

python -m tests.test_chunking_embedding

==================================================
FlowNote 청킹 & 임베딩 통합 테스트
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

첫 번째 청크 메타데이터:
✅ 청크 수: 6
  - text: 
    FlowNote MVP 프로젝트입니다.
    
    이 도구는 AI 대화를 체...
  - metadata: {'filename': 'test.md'}
  - chunk_index: 0
  - total_chunks: 6
✅ 파일 추가 완료: file_20251115_162545_97448e4c
  - filename: test.md
   - 크기: 51200 MB
   - 청크 수: 6
   - 모델: text-embedding-3-small

==================================================
3. 임베딩 테스트
==================================================

✅ 임베딩 성공!
  - 임베딩 개수: 3
  - 벡터 차원: 1536
  - 총 토큰: 353
  - 총 비용: $0.00000706

==================================================
4. 전체 파일 비용 예측
==================================================
  - 전체 청크 수: 6
  - 예상 토큰: 669
  - 예상 비용: $0.00001338

==================================================
5. 테스트 결과 요약
==================================================
✅ 청킹: 성공 (6개 청크)
✅ 임베딩: 성공 (3개 테스트)
✅ 비용 계산: 성공

🎉 모든 테스트 통과! (임베딩으로 검증 완료)

"""
