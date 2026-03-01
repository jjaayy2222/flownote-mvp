# scripts/bootstrap_index.py

import sys
import argparse
import asyncio
import logging
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.services.hybrid_search_service import HybridSearchService
from backend.chunking import TextChunker
from backend.api.models import PARACategory
from backend.config import PathConfig
import numpy as np


logger = logging.getLogger(__name__)


def _infer_category(file_path: Path) -> PARACategory | None:
    """
    파일의 부모 디렉터리 경로(parts)만을 기준으로 PARA 카테고리를 유추한다.
    파일명은 제외하여 `my_project_notes.md` 같은 파일이 잘못 분류되는 것을 방지한다.
    """
    dir_parts = [p.lower() for p in file_path.parent.parts]
    if "project" in dir_parts or "projects" in dir_parts:
        return PARACategory.PROJECTS
    if "area" in dir_parts or "areas" in dir_parts:
        return PARACategory.AREAS
    if "resource" in dir_parts or "resources" in dir_parts:
        return PARACategory.RESOURCES
    if "archive" in dir_parts or "archives" in dir_parts:
        return PARACategory.ARCHIVES
    return None


async def _process_and_index_file(
    file_path: Path,
    vault_path: Path,
    chunker: TextChunker,
    service: HybridSearchService,
    batch_size: int,
) -> tuple[int, int]:
    """
    단일 파일을 읽고 청킹한 뒤, batch_size 단위로 즉시 FAISS/BM25에 인덱싱한다.
    메모리에 모든 청크를 쌓지 않는 스트리밍 방식이다.

    Returns:
        (indexed_count, error_count): (인덱싱된 청크 수, 실패한 배치 수)
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        logger.warning("UnicodeDecodeError — 파일 스킵: %s", file_path.name)
        return 0, 0
    except OSError as e:
        logger.warning("파일 읽기 실패 (%s): %s", type(e).__name__, file_path.name)
        return 0, 0

    if not content.strip():
        return 0, 0

    category = _infer_category(file_path)
    metadata = {
        "source": str(file_path.relative_to(vault_path)),
        "filename": file_path.name,
        "category": category.value if category else None,
    }

    chunks = chunker.chunk_with_metadata(content, metadata)
    if not chunks:
        return 0, 0

    indexed_count = 0
    error_count = 0

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c["text"] for c in batch]
        doc_entries = [{"content": c["text"], "metadata": c["metadata"]} for c in batch]

        try:
            # BM25: rebuild=False로 추가만 (최종 일괄 build_index 호출 예정)
            service.bm25_retriever.add_documents(doc_entries, rebuild=False)

            # FAISS: 임베딩 즉시 생성 후 인덱싱 (OpenAI API 호출)
            emb_result = (
                service.faiss_retriever.embedding_generator.generate_embeddings(texts)
            )
            embeddings = np.array(emb_result["embeddings"], dtype=np.float32)
            service.faiss_retriever.add_documents(embeddings, doc_entries)

            indexed_count += len(batch)
        except Exception as e:
            logger.error(
                "배치 인덱싱 실패 (%s) — 파일: %s, 배치 오프셋: %d",
                type(e).__name__,
                file_path.name,
                i,
                exc_info=True,
            )
            error_count += 1

    return indexed_count, error_count


async def main() -> None:
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
        help="Batch size for embedding generation per file (default: 100)",
    )
    args = parser.parse_args()

    vault_path = Path(args.vault).resolve()
    if not vault_path.exists() or not vault_path.is_dir():
        logger.error("Vault 경로가 존재하지 않거나 디렉토리가 아닙니다: %s", args.vault)
        return

    logger.info("🚀 인덱스 부트스트랩 시작: %s", vault_path)

    # 1. 서비스 초기화
    service = HybridSearchService()

    if args.clear:
        logger.info("🗑️ 기존 인덱스 초기화 중...")
        service.faiss_retriever.clear()
        service.bm25_retriever.clear()

    # 청커 초기화
    chunker = TextChunker(chunk_size=500, chunk_overlap=50)

    # 2. 모든 마크다운 파일 탐색
    md_files = list(vault_path.rglob("*.md"))
    logger.info("📁 총 %d개의 마크다운 파일을 발견했습니다.", len(md_files))

    if not md_files:
        logger.info("ℹ️ 인덱싱할 마크다운 파일이 없습니다.")
        return

    # 3. 파일 단위 스트리밍 인덱싱 (메모리 누적 없음)
    total_indexed = 0
    total_errors = 0
    skipped_files = 0

    logger.info("📖 파일 단위 스트리밍 인덱싱 시작 (배치 크기: %d)...", args.batch_size)

    for file_idx, file_path in enumerate(md_files):
        indexed, errors = await _process_and_index_file(
            file_path=file_path,
            vault_path=vault_path,
            chunker=chunker,
            service=service,
            batch_size=args.batch_size,
        )

        if indexed == 0 and errors == 0:
            skipped_files += 1
        else:
            total_indexed += indexed
            total_errors += errors

        if (file_idx + 1) % 50 == 0:
            logger.info(
                "   - %d/%d 파일 완료 (인덱싱된 청크: %d)",
                file_idx + 1,
                len(md_files),
                total_indexed,
            )

    # 4. BM25 최종 인덱스 빌드
    logger.info("🏗️ BM25 인덱스 최종 재구성 중 (Rebuild)...")
    service.bm25_retriever.build_index()

    # 5. 인덱스 영속화
    logger.info("💾 모든 인덱스를 디스크에 저장 중...")
    service.save_indices()

    # 6. 결과 요약
    logger.info(
        "\n✨ 인덱싱 완료!\n"
        "   - 처리 파일 수  : %d개 (스킵: %d개)\n"
        "   - 인덱싱된 청크: %d개\n"
        "   - 실패 배치 수 : %d개\n"
        "   - 최종 인덱스 크기: %d개 청크\n"
        "   - 인덱스 저장 경로: %s",
        len(md_files) - skipped_files,
        skipped_files,
        total_indexed,
        total_errors,
        service.faiss_retriever.size(),
        PathConfig.FAISS_INDEX_DIR,
    )

    if total_errors > 0:
        logger.warning(
            "⚠️ %d개의 배치 인덱싱이 실패했습니다. 로그를 확인하세요.", total_errors
        )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 사용자에 의해 중단되었습니다.")
    except Exception as e:
        logger.exception("실행 중 치명적 오류 발생: %s", e)
