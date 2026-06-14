# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/metadata.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - 파일 메타데이터 관리
"""

import json
import os
import uuid  # 추가!
from datetime import datetime
from typing import Dict, List, Optional


class FileMetadata:
    """파일 메타데이터 관리 클래스"""

    def __init__(self, storage_path: str = "data/metadata.json"):
        """
        Args:
            storage_path: 메타데이터 저장 경로
        """
        self.storage_path = storage_path
        self.metadata: Dict[str, Dict] = {}
        self._load_metadata()

    def _load_metadata(self):
        """저장된 메타데이터 로드"""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    self.metadata = json.load(f)
            except Exception as e:
                print(f"메타데이터 로드 실패: {e}")
                self.metadata = {}
        else:
            # data 폴더 생성
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            self.metadata = {}

    def _save_metadata(self):
        """메타데이터 저장"""
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"메타데이터 저장 실패: {e}")

    def add_file(
        self,
        file_name: str,
        file_size: int,
        chunk_count: int,
        embedding_dim: int,
        model: str = "text-embedding-3-small",
    ) -> str:
        """
        파일 메타데이터 추가

        Args:
            file_name: 파일명
            file_size: 파일 크기 (bytes)
            chunk_count: 청크 개수
            embedding_dim: 임베딩 차원
            model: 사용된 임베딩 모델

        Returns:
            file_id: 생성된 파일 ID
        """
        # 파일 ID 생성 (타임스탬프 + UUID로 고유성 보장!)
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

    def get_file(self, file_id: str) -> Optional[Dict]:
        """
        파일 메타데이터 조회

        Args:
            file_id: 파일 ID

        Returns:
            메타데이터 딕셔너리 또는 None
        """
        return self.metadata.get(file_id)

    def get_all_files(self) -> Dict[str, Dict]:
        """
        모든 파일 메타데이터 조회

        Returns:
            전체 메타데이터 딕셔너리
        """
        return self.metadata

    def delete_file(self, file_id: str) -> bool:
        """
        파일 메타데이터 삭제

        Args:
            file_id: 파일 ID

        Returns:
            삭제 성공 여부
        """
        if file_id in self.metadata:
            del self.metadata[file_id]
            self._save_metadata()
            return True
        return False

    def get_statistics(self) -> Dict:
        """
        전체 통계 계산

        Returns:
            통계 딕셔너리
        """
        if not self.metadata:
            return {
                "total_files": 0,
                "total_chunks": 0,
                "total_size_mb": 0,
                "models_used": [],
            }

        total_chunks = sum(m["chunk_count"] for m in self.metadata.values())
        total_size = sum(m["file_size"] for m in self.metadata.values())
        models = list(set(m["embedding_model"] for m in self.metadata.values()))

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
    print(f"📄 첫 번째 파일:")
    print(f"   - 파일명: {file_info['file_name']}")
    print(f"   - 크기: {file_info['file_size_mb']} MB")
    print(f"   - 청크 수: {file_info['chunk_count']}")
    print(f"   - 모델: {file_info['embedding_model']}")

    file_info2 = metadata.get_file(file_id2)
    print(f"\n📄 두 번째 파일:")
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
    print(f"📊 통계:")
    print(f"   - 총 파일: {stats['total_files']}개")
    print(f"   - 총 청크: {stats['total_chunks']}개")
    print(f"   - 총 크기: {stats['total_size_mb']} MB")
    print(f"   - 사용 모델: {stats['models_used']}")

    print("\n" + "=" * 50)
    print("테스트 완료!")
    print("=" * 50)


"""result

    ==================================================
    파일 메타데이터 테스트
    ==================================================

    1. 파일 추가 테스트
    --------------------------------------------------
    ✅ 파일 추가 완료: file_20251025_131227_d9977552
    ✅ 파일 추가 완료: file_20251025_131227_2e480777

    2. 파일 조회 테스트
    --------------------------------------------------
    📄 첫 번째 파일:
        - 파일명: test_document.txt
        - 크기: 0.05 MB
        - 청크 수: 10
        - 모델: text-embedding-3-small

    📄 두 번째 파일:
        - 파일명: large_document.txt
        - 크기: 2.0 MB
        - 청크 수: 50
        - 모델: text-embedding-3-large

    3. 전체 파일 목록
    --------------------------------------------------
    📚 등록된 파일: 2개
        - file_20251025_131227_d9977552: test_document.txt
        - file_20251025_131227_2e480777: large_document.txt

    4. 통계 테스트
    --------------------------------------------------
    📊 통계:
        - 총 파일: 2개
        - 총 청크: 60개
        - 총 크기: 2.05 MB
        - 사용 모델: ['text-embedding-3-small', 'text-embedding-3-large']

    ==================================================
    테스트 완료!
    ==================================================

"""


"""result_2

    ==================================================
    파일 메타데이터 테스트
    ==================================================

    1. 파일 추가 테스트
    --------------------------------------------------
    ✅ 파일 추가 완료: file_20251025_145527_16a6f607
    ✅ 파일 추가 완료: file_20251025_145527_edb1679e

    2. 파일 조회 테스트
    --------------------------------------------------
    📄 첫 번째 파일:
        - 파일명: test_document.txt
        - 크기: 0.05 MB
        - 청크 수: 10
        - 모델: text-embedding-3-small

    📄 두 번째 파일:
        - 파일명: large_document.txt
        - 크기: 2.0 MB
        - 청크 수: 50
        - 모델: text-embedding-3-large

    3. 전체 파일 목록
    --------------------------------------------------
    📚 등록된 파일: 4개
        - file_20251025_131227_d9977552: test_document.txt
        - file_20251025_131227_2e480777: large_document.txt
        - file_20251025_145527_16a6f607: test_document.txt
        - file_20251025_145527_edb1679e: large_document.txt

    4. 통계 테스트
    --------------------------------------------------
    📊 통계:
        - 총 파일: 4개
        - 총 청크: 120개
        - 총 크기: 4.1 MB
        - 사용 모델: ['text-embedding-3-small', 'text-embedding-3-large']

    ==================================================
    테스트 완료!
    ==================================================

"""


"""result_3

    ==================================================
    파일 메타데이터 테스트
    ==================================================

    1. 파일 추가 테스트
    --------------------------------------------------
    ✅ 파일 추가 완료: file_20251025_151445_84fb1fd3
    ✅ 파일 추가 완료: file_20251025_151445_52a6b101

    2. 파일 조회 테스트
    --------------------------------------------------
    📄 첫 번째 파일:
        - 파일명: test_document.txt
        - 크기: 0.05 MB
        - 청크 수: 10
        - 모델: text-embedding-3-small

    📄 두 번째 파일:
        - 파일명: large_document.txt
        - 크기: 2.0 MB
        - 청크 수: 50
        - 모델: text-embedding-3-large

    3. 전체 파일 목록
    --------------------------------------------------
    📚 등록된 파일: 6개
        - file_20251025_131227_d9977552: test_document.txt
        - file_20251025_131227_2e480777: large_document.txt
        - file_20251025_145527_16a6f607: test_document.txt
        - file_20251025_145527_edb1679e: large_document.txt
        - file_20251025_151445_84fb1fd3: test_document.txt
        - file_20251025_151445_52a6b101: large_document.txt

    4. 통계 테스트
    --------------------------------------------------
    📊 통계:
        - 총 파일: 6개
        - 총 청크: 180개
        - 총 크기: 6.15 MB
        - 사용 모델: ['text-embedding-3-small', 'text-embedding-3-large']

    ==================================================
    테스트 완료!
    ==================================================

"""
