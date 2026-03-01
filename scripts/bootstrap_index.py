# scripts/bootstrap_index.py

import sys
import os
import argparse
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.services.hybrid_search_service import HybridSearchService
from backend.chunking import TextChunker
from backend.api.models import PARACategory
import numpy as np


async def main():
    parser = argparse.ArgumentParser(
        description="FlowNote Hybrid Search Index Bootstrapper"
    )
    parser.add_argument(
        "--vault", type=str, required=True, help="Path to Obsidian Vault directory"
    )
    parser.add_argument(
        "--clear", action="store_true", help="Clear existing index before starting"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for embedding generation",
    )
    args = parser.parse_args()

    vault_path = Path(args.vault).resolve()
    if not vault_path.exists() or not vault_path.is_dir():
        print(f"❌ Vault 경로가 존재하지 않거나 디렉토리가 아닙니다: {args.vault}")
        return

    print(f"🚀 인덱스 부트스트랩 시작: {vault_path}")

    # 1. 서비스 초기화
    # HybridSearchService는 내부적으로 default dimension(1536) 등을 관리함
    service = HybridSearchService()

    if args.clear:
        print("🗑️ 기존 인덱스 초기화 중...")
        service.faiss_retriever.clear()
        service.bm25_retriever.clear()

    # 청커 초기화 (기본값: size 500, overlap 50)
    chunker = TextChunker(chunk_size=500, chunk_overlap=50)

    # 2. 모든 마크다운 파일 찾기
    md_files = list(vault_path.rglob("*.md"))
    print(f"📁 총 {len(md_files)}개의 마크다운 파일을 발견했습니다.")

    # 3. 파일 처리 및 청크 생성
    all_chunks = []

    print("📖 파일 읽기 및 청킹 진행 중...")
    for i, file_path in enumerate(md_files):
        try:
            # 경로에서 PARA 카테고리 유추
            category = None
            path_parts = [p.lower() for p in file_path.parts]

            # 폴더명에 기반한 카테고리 매핑
            if "project" in path_parts or "projects" in path_parts:
                category = PARACategory.PROJECTS
            elif "area" in path_parts or "areas" in path_parts:
                category = PARACategory.AREAS
            elif "resource" in path_parts or "resources" in path_parts:
                category = PARACategory.RESOURCES
            elif "archive" in path_parts or "archives" in path_parts:
                category = PARACategory.ARCHIVES

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if not content.strip():
                continue

            # 메타데이터 구성
            metadata = {
                "source": str(file_path.relative_to(vault_path)),
                "filename": file_path.name,
                "category": category.value if category else None,
            }

            chunks = chunker.chunk_with_metadata(content, metadata)
            all_chunks.extend(chunks)

            if (i + 1) % 50 == 0:
                print(f"   - {i + 1}/{len(md_files)}개 파일 처리 완료...")

        except Exception as e:
            print(f"⚠️ {file_path} 처리 중 오류 발생: {e}")

    print(f"✅ 총 {len(all_chunks)}개의 청크가 생성되었습니다.")

    if not all_chunks:
        print("ℹ️ 인덱싱할 데이터가 없습니다.")
        return

    # 4. 인덱스에 배치 추가
    batch_size = args.batch_size
    total_batches = (len(all_chunks) + batch_size - 1) // batch_size

    print(f"📡 인덱싱 및 임베딩 생성 시작 (배치 크기: {batch_size})...")

    for i in range(0, len(all_chunks), batch_size):
        batch_idx = i // batch_size + 1
        batch = all_chunks[i : i + batch_size]

        texts = [c["text"] for c in batch]
        # 리트리버가 기대하는 문서 포맷: {"content": str, "metadata": dict}
        doc_entries = [{"content": c["text"], "metadata": c["metadata"]} for c in batch]

        try:
            # 4-1. BM25 추가 (마지막에 한꺼번에 빌드하기 위해 rebuild=False)
            service.bm25_retriever.add_documents(doc_entries, rebuild=False)

            # 4-2. FAISS 추가
            # 임베딩 생성 (OpenAI API 호출 발생)
            emb_result = (
                service.faiss_retriever.embedding_generator.generate_embeddings(texts)
            )
            embeddings = np.array(emb_result["embeddings"], dtype=np.float32)
            service.faiss_retriever.add_documents(embeddings, doc_entries)

            print(
                f"   - [{batch_idx}/{total_batches}] 배치 완료 (현재 청크: {min(i + batch_size, len(all_chunks))}/{len(all_chunks)})"
            )

        except Exception as e:
            print(f"❌ 배치 {batch_idx} 처리 중 오류 발생: {e}")

    # 5. 최종 인덱스 빌드 및 저장
    print("🏗️ BM25 인덱싱 최종 재구성 중 (Rebuild)...")
    service.bm25_retriever.build_index()

    print("💾 모든 인덱스를 디스크에 저장 중...")
    service.save_indices()

    print(f"\n✨ 인덱싱 완료!")
    print(f"   - 최종 인덱스 크기: {service.faiss_retriever.size()}개 청크")
    print(f"   - 인덱스 저장 경로: {PathConfig.FAISS_INDEX_DIR}")


if __name__ == "__main__":
    # 로깅 레벨 조정 (너무 상세한 로그 방지)
    import logging
    from backend.config import PathConfig

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 사용자에 의해 중단되었습니다.")
    except Exception as e:
        print(f"\n❌ 실행 중 치명적 오류 발생: {e}")
