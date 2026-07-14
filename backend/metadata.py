# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/metadata.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
[KO] FlowNote MVP - 파일 메타데이터 관리
[EN] FlowNote MVP - File Metadata Management

[KO] 파일 업로드 시 메타데이터(파일명, 크기, 청크 수, 임베딩 차원 등)를 추출·정규화하고
     로컬 JSON 파일에 영속화하여 관리하는 모듈입니다.
[EN] Extracts and normalizes file metadata (name, size, chunk count, embedding dimensions, etc.)
     upon upload, and persists it to a local JSON file.
"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, TypedDict

logger = logging.getLogger(__name__)


class FileMetadataRecord(TypedDict):
    """
    [KO] 개별 파일의 메타데이터 레코드 타입
    [EN] TypedDict for a single file's metadata record
    """

    file_name: str
    file_size: int
    file_size_mb: float
    chunk_count: int
    embedding_dim: int
    embedding_model: str
    upload_time: str
    created_at: str


class MetadataStatistics(TypedDict):
    """
    [KO] 전체 파일 메타데이터 통계 반환 타입
    [EN] Return type for overall file metadata statistics
    """

    total_files: int
    total_chunks: int
    total_size_mb: float
    models_used: List[str]


class FileMetadata:
    """
    [KO] 파일 메타데이터를 로컬 JSON 파일에 영속화하고 관리하는 클래스.
    [EN] A class to persist and manage file metadata in a local JSON file.
    """

    def __init__(self, storage_path: str = "data/metadata.json"):
        """
        [KO] 메타데이터 저장 경로를 설정하고, 기존에 저장된 데이터를 로드합니다.
        [EN] Sets the metadata storage path and loads any previously saved data.

        Args:
            storage_path (str): [KO] 메타데이터 JSON 파일 저장 경로 (기본값: "data/metadata.json")
                                 / [EN] Path to the metadata JSON file (default: "data/metadata.json")
        """
        self.storage_path = storage_path
        self.metadata: Dict[str, FileMetadataRecord] = {}
        self._load_metadata()

    def _load_metadata(self) -> None:
        """
        [KO] JSON 파일에서 저장된 메타데이터를 메모리로 로드합니다.
             파일이 없을 경우 저장 디렉토리를 생성하고 빈 상태로 초기화합니다.
        [EN] Loads saved metadata from the JSON file into memory.
             If the file does not exist, creates the storage directory and initializes an empty state.
        """
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                # [KO] json.load 결과가 dict인지 경량 검증 (손상된 파일 대비)
                # [EN] Lightweight validation to ensure json.load result is a dict (guards against corrupted files)
                if isinstance(loaded, dict):
                    self.metadata = loaded
                else:
                    logger.warning(
                        "메타데이터 형식 오류: 딕셔너리가 아닙니다. 초기화합니다.",
                        extra={"storage_path": self.storage_path},
                    )
                    self.metadata = {}
            except json.JSONDecodeError as e:
                logger.warning(
                    "메타데이터 파일 JSON 파싱 실패: %s",
                    e,
                    exc_info=True,
                    extra={"storage_path": self.storage_path},
                )
                self.metadata = {}
            except OSError as e:
                logger.error(
                    "메타데이터 파일 읽기 실패: %s",
                    e,
                    exc_info=True,
                    extra={"storage_path": self.storage_path},
                )
                self.metadata = {}
        else:
            # [KO] storage_path에 디렉터리 구성 요소가 있을 때만 폴더 생성
            # [EN] Only create directory if storage_path contains a directory component
            storage_dir = os.path.dirname(self.storage_path)
            if storage_dir:
                os.makedirs(storage_dir, exist_ok=True)
            self.metadata = {}

    def _save_metadata(self) -> None:
        """
        [KO] 현재 메모리에 있는 메타데이터를 JSON 파일에 영속화합니다.
        [EN] Persists the current in-memory metadata to the JSON file.
        """
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error(
                "메타데이터 파일 저장 실패: %s",
                e,
                exc_info=True,
                extra={"storage_path": self.storage_path},
            )

    def add_file(
        self,
        file_name: str,
        file_size: int,
        chunk_count: int,
        embedding_dim: int,
        model: str = "text-embedding-3-small",
    ) -> str:
        """
        [KO] 새로운 파일의 메타데이터를 생성하고 저장소에 추가합니다.
             파일 ID는 타임스탬프와 UUID를 조합하여 고유성을 보장합니다.
        [EN] Creates and adds metadata for a new file to the storage.
             The file ID is composed of a timestamp and UUID to ensure uniqueness.

        Args:
            file_name (str): [KO] 업로드한 파일의 이름
                             / [EN] Name of the uploaded file.
            file_size (int): [KO] 파일 크기 (바이트 단위)
                             / [EN] File size in bytes.
            chunk_count (int): [KO] 파일이 분할된 청크의 개수
                               / [EN] Number of chunks the file was split into.
            embedding_dim (int): [KO] 생성된 임베딩 벡터의 차원 수
                                 / [EN] Dimension of the generated embedding vectors.
            model (str): [KO] 임베딩 생성에 사용된 모델 이름 (기본값: "text-embedding-3-small")
                         / [EN] Name of the model used for embedding generation (default: "text-embedding-3-small").

        Returns:
            str: [KO] 생성된 고유 파일 ID (예: "file_20251025_131227_d9977552")
                 / [EN] The generated unique file ID (e.g., "file_20251025_131227_d9977552").
        """
        # 파일 ID 생성 (타임스탬프 + UUID로 고유성 보장)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]  # UUID의 앞 8자리
        file_id = f"file_{timestamp}_{unique_id}"

        # 메타데이터 생성
        self.metadata[file_id] = {
            "file_name": file_name,
            "file_size": file_size,
            "file_size_mb": round(file_size / (1024 * 1024), 2),
            "chunk_count": chunk_count,
            "embedding_dim": embedding_dim,
            "embedding_model": model,
            "upload_time": datetime.now().isoformat(),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # 저장
        self._save_metadata()

        return file_id

    def get_file(self, file_id: str) -> Optional[FileMetadataRecord]:
        """
        [KO] 특정 파일 ID에 해당하는 메타데이터를 반환합니다.
        [EN] Returns the metadata corresponding to a specific file ID.

        Args:
            file_id (str): [KO] 조회할 파일의 고유 ID
                           / [EN] The unique ID of the file to look up.

        Returns:
            Optional[FileMetadataRecord]: [KO] 해당 파일의 메타데이터 딕셔너리, 존재하지 않으면 None
                                         / [EN] The file's metadata dictionary, or None if not found.
        """
        return self.metadata.get(file_id)

    def get_all_files(self) -> Dict[str, FileMetadataRecord]:
        """
        [KO] 저장된 모든 파일의 메타데이터를 반환합니다.
        [EN] Returns the metadata of all stored files.

        Returns:
            Dict[str, FileMetadataRecord]: [KO] 파일 ID를 키로 하는 전체 메타데이터 딕셔너리
                                           / [EN] A dictionary of all metadata keyed by file ID.
        """
        return self.metadata

    def delete_file(self, file_id: str) -> bool:
        """
        [KO] 특정 파일 ID에 해당하는 메타데이터를 삭제합니다.
        [EN] Deletes the metadata corresponding to a specific file ID.

        Args:
            file_id (str): [KO] 삭제할 파일의 고유 ID
                           / [EN] The unique ID of the file to delete.

        Returns:
            bool: [KO] 삭제 성공 시 True, 파일 ID가 존재하지 않으면 False
                  / [EN] True if deletion was successful, False if the file ID was not found.
        """
        if file_id in self.metadata:
            del self.metadata[file_id]
            self._save_metadata()
            return True
        return False

    def get_statistics(self) -> MetadataStatistics:
        """
        [KO] 저장된 전체 파일 메타데이터를 바탕으로 통계 정보를 계산합니다.
        [EN] Calculates statistical information based on all stored file metadata.

        Returns:
            MetadataStatistics: [KO] 총 파일 수, 총 청크 수, 총 크기(MB), 사용된 모델 목록을 포함한 통계 딕셔너리
                                 / [EN] Statistics dictionary containing total files, chunks, size (MB), and models used.
        """
        if not self.metadata:
            return {
                "total_files": 0,
                "total_chunks": 0,
                "total_size_mb": 0.0,
                "models_used": [],
            }

        total_chunks = sum(m["chunk_count"] for m in self.metadata.values())
        total_size = sum(m["file_size"] for m in self.metadata.values())
        models = sorted({m["embedding_model"] for m in self.metadata.values()})

        return {
            "total_files": len(self.metadata),
            "total_chunks": total_chunks,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "models_used": models,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 테스트 코드
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    print("=" * 50)
    print("파일 메타데이터 테스트")
    print("=" * 50)

    # 메타데이터 관리자 생성
    metadata = FileMetadata()

    # 테스트 파일 추가
    print("\n1. 파일 추가 테스트")
    print("-" * 50)

    file_id1 = metadata.add_file(
        file_name="test_document.txt",
        file_size=1024 * 50,  # 50KB
        chunk_count=10,
        embedding_dim=1536,
        model="text-embedding-3-small",
    )
    print(f"✅ 파일 추가 완료: {file_id1}")

    file_id2 = metadata.add_file(
        file_name="large_document.txt",
        file_size=1024 * 1024 * 2,  # 2MB
        chunk_count=50,
        embedding_dim=3072,
        model="text-embedding-3-large",
    )
    print(f"✅ 파일 추가 완료: {file_id2}")

    # 파일 조회
    print("\n2. 파일 조회 테스트")
    print("-" * 50)

    file_info = metadata.get_file(file_id1)
    print("📄 첫 번째 파일:")
    if file_info is not None:
        print(f"   - 파일명: {file_info['file_name']}")
        print(f"   - 크기: {file_info['file_size_mb']} MB")
        print(f"   - 청크 수: {file_info['chunk_count']}")
        print(f"   - 모델: {file_info['embedding_model']}")

    file_info2 = metadata.get_file(file_id2)
    print("\n📄 두 번째 파일:")
    if file_info2 is not None:
        print(f"   - 파일명: {file_info2['file_name']}")
        print(f"   - 크기: {file_info2['file_size_mb']} MB")
        print(f"   - 청크 수: {file_info2['chunk_count']}")
        print(f"   - 모델: {file_info2['embedding_model']}")

    # 전체 파일 확인
    print("\n3. 전체 파일 목록")
    print("-" * 50)
    all_files = metadata.get_all_files()
    print(f"📚 등록된 파일: {len(all_files)}개")
    for fid, info in all_files.items():
        print(f"   - {fid}: {info['file_name']}")

    # 통계
    print("\n4. 통계 테스트")
    print("-" * 50)

    stats = metadata.get_statistics()
    print("📊 통계:")
    print(f"   - 총 파일: {stats['total_files']}개")
    print(f"   - 총 청크: {stats['total_chunks']}개")
    print(f"   - 총 크기: {stats['total_size_mb']} MB")
    print(f"   - 사용 모델: {stats['models_used']}")

    print("\n" + "=" * 50)
    print("테스트 완료!")
    print("=" * 50)
