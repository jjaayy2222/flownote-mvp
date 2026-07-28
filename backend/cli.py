"""
[KO] FlowNote CLI - MCP 통합 인터페이스
[EN] FlowNote CLI - MCP Integration Interface

[KO] MCP가 HTTP 없이 서비스를 직접 호출하는 방법을 시연하는 모듈입니다.
[EN] Demonstrates how MCP can call services directly without HTTP.
"""

import asyncio
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Service imports
from backend.services.classification_service import ClassificationService
from backend.services.onboarding_service import OnboardingService


@dataclass
class UserContextData:
    """[KO] 사용자 컨텍스트 데이터 구조"""

    occupation: Optional[str] = None
    areas: Optional[list[str]] = None


class FlowNoteCLI:
    """
    [KO] FlowNote CLI - MCP 통합 시뮬레이션
    [EN] FlowNote CLI - MCP Integration Simulation
    """

    def __init__(self):
        self.classification_service = ClassificationService()
        self.onboarding_service = OnboardingService()

    def _get_user_context(self, user_id: str) -> UserContextData:
        """[KO] 사용자 컨텍스트(occupation, areas)를 조회하고 검증하여 반환합니다."""
        valid_occ = None
        valid_areas = None
        try:
            status = self.onboarding_service.get_user_status(user_id)
            if status and status.get("status") == "success":
                if raw_areas := status.get("areas"):
                    if isinstance(raw_areas, list):
                        valid_areas = [str(a) for a in raw_areas]
                    elif isinstance(raw_areas, str):
                        valid_areas = [
                            a.strip() for a in raw_areas.split(",") if a.strip()
                        ]

                if isinstance(raw_occ := status.get("occupation"), str):
                    valid_occ = raw_occ
        except Exception:
            logger.exception("⚠️ 사용자 정보 조회 실패 (무시)")

        return UserContextData(occupation=valid_occ, areas=valid_areas)

    async def classify_file(self, file_path: str, user_id: Optional[str] = None):
        """
        [KO] 단일 파일 분류를 실행합니다 (MCP 직접 호출용).
        [EN] Executes single file classification (for direct MCP calls).

        Args:
            file_path: [KO] 로컬 파일 경로 / [EN] Local file path
            user_id: [KO] 사용자 ID (선택) / [EN] User ID (optional)

        Returns:
            [KO] 분류 결과 객체(ClassifyResponse), 실패 시 None / [EN] Classification result object (ClassifyResponse), or None on failure
        """
        try:
            path_obj = Path(file_path)
            if not path_obj.exists():
                print(f"❌ 파일을 찾을 수 없습니다: {file_path}")
                return None

            if not path_obj.is_file():
                print(f"❌ 파일이 아닙니다: {file_path}")
                return None

            # 파일 읽기 (인코딩 에러 처리)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    text = f.read()
            except UnicodeDecodeError:
                print(
                    f"❌ 텍스트 파일이 아니거나 인코딩을 지원하지 않습니다: {file_path}"
                )
                return None
            except Exception as e:
                print(f"❌ 파일 읽기 오류: {e}")
                return None

            # 보안: 절대 경로 노출 방지를 위해 해시값 사용 (SHA256)
            import hashlib

            # 파일 내용 + 파일명 조합으로 고유성 확보
            content_preview = text[:100]  # 처음 100자만 해시에 사용
            hash_input = f"{path_obj.name}_{content_preview}".encode("utf-8")
            file_hash = hashlib.sha256(hash_input).hexdigest()[
                :12
            ]  # 12자리로 충돌 최소화
            safe_file_id = f"{path_obj.name}_{file_hash}"

            # 사용자 컨텍스트 가져오기
            user_context = UserContextData()
            if user_id:
                user_context = self._get_user_context(user_id)

            # 분류 실행 (HTTP 없이 직접 호출!)
            print(f"🔍 분류 시작: {path_obj.name} (User: {user_id or 'Anonymous'})")
            result = await self.classification_service.classify(
                text=text,
                user_id=user_id,
                file_id=safe_file_id,
                occupation=user_context.occupation,
                areas=user_context.areas,
            )

            print(f"✅ 분류 완료: {result.category}")
            print(f"   키워드: {result.keyword_tags[:5]}")
            print(f"   신뢰도: {result.confidence:.2f}")

            return result

        except Exception as e:
            print(f"❌ 분류 실패: {e}")
            return None

    async def batch_classify(self, directory: str, user_id: Optional[str] = None):
        """
        [KO] 지정한 디렉토리 내의 모든 텍스트/마크다운 파일을 분류합니다. (MCP 워크스페이스 전체 분류용)
        [EN] Classifies all text/markdown files in a specified directory. (For MCP workspace-wide classification)

        Args:
            directory: [KO] 분석할 디렉토리 경로 / [EN] Directory path to analyze
            user_id: [KO] 사용자 ID (선택) / [EN] User ID (optional)

        Returns:
            [KO] 각 파일의 분류 결과 딕셔너리 리스트 (키: file, category, confidence) / [EN] List of classification result dicts (keys: file, category, confidence)
        """
        dir_path = Path(directory)

        if not dir_path.is_dir():
            print(f"❌ 디렉토리가 아닙니다: {directory}")
            return

        files = list(dir_path.glob("*.txt")) + list(dir_path.glob("*.md"))
        print(f"📁 발견된 파일: {len(files)}개")

        results = []
        for file_path in files:
            print(f"\n처리 중: {file_path.name}")
            result = await self.classify_file(str(file_path), user_id)
            if result:
                results.append(
                    {
                        "file": file_path.name,
                        "category": result.category,
                        "confidence": result.confidence,
                    }
                )

        # 결과 요약
        print("\n" + "=" * 50)
        print("분류 결과 요약:")
        print("=" * 50)
        for r in results:
            print(f"{r['file']:30} → {r['category']:15} ({r['confidence']:.2f})")

        return results


async def main():
    """
    [KO] CLI 실행 진입점 예제
    [EN] CLI execution entry point example
    """
    cli = FlowNoteCLI()

    if len(sys.argv) < 2:
        print("사용법:")
        print("  python -m backend.cli classify <file_path> [user_id]")
        print("  python -m backend.cli batch <directory> [user_id]")
        return

    command = sys.argv[1]

    if command == "classify" and len(sys.argv) >= 3:
        file_path = sys.argv[2]
        user_id = sys.argv[3] if len(sys.argv) > 3 else None
        await cli.classify_file(file_path, user_id)

    elif command == "batch" and len(sys.argv) >= 3:
        directory = sys.argv[2]
        user_id = sys.argv[3] if len(sys.argv) > 3 else None
        await cli.batch_classify(directory, user_id)

    else:
        print("❌ 잘못된 명령어")


if __name__ == "__main__":
    # 로깅 설정 (CLI 실행 시에만 적용)
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
