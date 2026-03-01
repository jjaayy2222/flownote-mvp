# scripts/bootstrap_index.py
#
# 실행 방법:
#   python scripts/bootstrap_index.py --vault /path/to/vault
#   또는
#   PYTHONPATH=$(pwd) python scripts/bootstrap_index.py --vault /path/to/vault
#
# sys.path 조작은 이 스크립트가 단독 CLI 유틸리티로 설계되었기 때문이며,
# poetry/setuptools 기반 패키지 구조가 도입되면 Entry Point로 대체할 수 있습니다.

import sys
import argparse
import asyncio
import logging
from pathlib import Path
from typing import Optional

# 프로젝트 루트를 sys.path에 추가 (단독 CLI 스크립트 표준 관행)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.services.hybrid_search_service import HybridSearchService
from backend.chunking import TextChunker
from backend.api.models import PARACategory
from backend.config import PathConfig
import numpy as np


logger = logging.getLogger(__name__)


def _infer_category(file_path: Path) -> Optional[PARACategory]:
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


async def _generate_embeddings_async(
    service: HybridSearchService,
    texts: list[str],
    semaphore: asyncio.Semaphore,
) -> Optional[np.ndarray]:
    """
    Semaphore를 통해 동시 요청 수를 제어하며 임베딩을 생성한다.
    I/O 바운드 작업(OpenAI API 호출)이므로 asyncio로 병렬화 가능하다.

    Returns:
        임베딩 배열, 또는 실패 시 None
    """
    async with semaphore:
        try:
            # generate_embeddings는 동기 함수이므로 스레드풀에서 실행
            loop = asyncio.get_event_loop()
            emb_result = await loop.run_in_executor(
                None,
                service.faiss_retriever.embedding_generator.generate_embeddings,
                texts,
            )
            return np.array(emb_result["embeddings"], dtype=np.float32)
        except Exception as e:
            logger.error(
                "임베딩 생성 실패 (%s): 텍스트 %d건",
                type(e).__name__,
                len(texts),
                exc_info=True,
            )
            return None


async def _process_file(
    file_path: Path,
    vault_path: Path,
    chunker: TextChunker,
    batch_size: int,
) -> tuple[list[list[dict]], list[str], int]:
    """
    파일을 읽고 청킹하여 (배치 doc_entries 리스트, 배치 texts 리스트, 스킵 여부)를 반환한다.
    인덱싱 자체는 수행하지 않으므로 완전히 순수 함수다.

    Returns:
        (batched_docs, batched_texts, error_flag): 배치 단위 문서·텍스트, 파일 오류 여부(0/1)
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        logger.warning("UnicodeDecodeError — 파일 스킵: %s", file_path.name)
        return [], [], 0
    except OSError as e:
        logger.warning("파일 읽기 실패 (%s): %s", type(e).__name__, file_path.name)
        return [], [], 0

    if not content.strip():
        return [], [], 0

    category = _infer_category(file_path)
    metadata = {
        "source": str(file_path.relative_to(vault_path)),
        "filename": file_path.name,
        "category": category.value if category else None,
    }

    chunks = chunker.chunk_with_metadata(content, metadata)
    if not chunks:
        return [], [], 0

    # 배치 단위로 분할
    batched_docs = []
    batched_texts = []
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        batched_docs.append(
            [{"content": c["text"], "metadata": c["metadata"]} for c in batch]
        )
        batched_texts.append([c["text"] for c in batch])

    return batched_docs, batched_texts, 0


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
        help="Batch size for embedding generation per file chunk (default: 100)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help=(
            "Max concurrent OpenAI embedding API requests (default: 5). "
            "Increase for higher throughput; decrease to respect rate limits."
        ),
    )
    args = parser.parse_args()

    vault_path = Path(args.vault).resolve()
    if not vault_path.exists() or not vault_path.is_dir():
        logger.error("Vault 경로가 존재하지 않거나 디렉토리가 아닙니다: %s", args.vault)
        return

    logger.info("🚀 인덱스 부트스트랩 시작: %s", vault_path)
    logger.info(
        "   - 배치 크기: %d  |  최대 동시 임베딩 요청: %d",
        args.batch_size,
        args.concurrency,
    )

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

    # 3. 동시 임베딩 생성 + 순차 인덱싱
    #
    # 설계 원칙:
    #   - 임베딩 생성(I/O 바운드): Semaphore로 동시 요청 수 제한하여 병렬 처리
    #   - 리트리버 add_documents(CPU/메모리): thread-safe하지 않으므로 반드시 순차 처리
    #   → 임베딩 수집 완료 후 인덱싱을 순서대로 실행하는 투-페이즈 방식
    #
    semaphore = asyncio.Semaphore(args.concurrency)

    total_indexed = 0
    total_errors = 0
    skipped_files = 0

    logger.info("📖 임베딩 병렬 생성 + 순차 인덱싱 시작...")

    for file_idx, file_path in enumerate(md_files):
        # Phase 1: 파일 읽기/청킹 (순수, 부작용 없음)
        batched_docs, batched_texts, _ = await _process_file(
            file_path=file_path,
            vault_path=vault_path,
            chunker=chunker,
            batch_size=args.batch_size,
        )

        if not batched_docs:
            skipped_files += 1
            continue

        # Phase 2: 배치별 임베딩 동시 생성 (I/O 병렬화, Semaphore 제어)
        embed_tasks = [
            _generate_embeddings_async(service, texts, semaphore)
            for texts in batched_texts
        ]
        embeddings_list: list[Optional[np.ndarray]] = await asyncio.gather(
            *embed_tasks, return_exceptions=False
        )

        # Phase 3: 순차 인덱싱 (thread-safe 보장을 위해 직렬 실행)
        for doc_entries, embeddings in zip(batched_docs, embeddings_list):
            if embeddings is None:
                total_errors += 1
                continue
            try:
                service.bm25_retriever.add_documents(doc_entries, rebuild=False)
                service.faiss_retriever.add_documents(embeddings, doc_entries)
                total_indexed += len(doc_entries)
            except Exception as e:
                logger.error(
                    "인덱싱 실패 (%s) — 파일: %s",
                    type(e).__name__,
                    file_path.name,
                    exc_info=True,
                )
                total_errors += 1

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
        logger.warning("⚠️ %d개의 배치가 실패했습니다. 로그를 확인하세요.", total_errors)


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
