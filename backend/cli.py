"""
CLI Interface for MCP Integration
- Demonstrates how MCP can call services directly without HTTP
"""

import asyncio
import sys
from pathlib import Path
import logging

# Service imports
from backend.services.classification_service import ClassificationService
from backend.services.onboarding_service import OnboardingService

# 로깅 설정 (CLI에서는 간단하게 출력)
logging.basicConfig(level=logging.WARNING)


class FlowNoteCLI:
    """FlowNote CLI - MCP 통합 시뮬레이션"""

    def __init__(self):
        self.classification_service = ClassificationService()
        self.onboarding_service = OnboardingService()

    async def classify_file(self, file_path: str, user_id: str = None):
        """파일 분류 (MCP가 이렇게 호출할 것)

        Args:
            file_path: 로컬 파일 경로
            user_id: 사용자 ID (선택)
        """
        try:
            path_obj = Path(file_path)
            if not path_obj.exists():
                print(f"❌ 파일을 찾을 수 없습니다: {file_path}")
                return None

            # 파일 읽기
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()

            # 사용자 컨텍스트 가져오기
            user_context = {}
            if user_id:
                # OnboardingService를 통해 사용자 정보 조회 (실제 DB 연동 시)
                # 현재는 mock 데이터나 로직에 따라 다를 수 있음
                try:
                    status = self.onboarding_service.get_user_status(user_id)
                    if status and status.get("status") == "success":
                        user_context = {
                            "occupation": status.get("occupation"),
                            "areas": status.get("areas", []),
                        }
                except Exception as e:
                    print(f"⚠️ 사용자 정보 조회 실패 (무시): {e}")

            # 분류 실행 (HTTP 없이 직접 호출!)
            print(f"🔍 분류 시작: {path_obj.name} (User: {user_id or 'Anonymous'})")
            result = await self.classification_service.classify(
                text=text,
                user_id=user_id,
                file_id=path_obj.name,
                occupation=user_context.get("occupation"),
                areas=user_context.get("areas"),
            )

            print(f"✅ 분류 완료: {result.category}")
            print(f"   키워드: {result.keyword_tags[:5]}")
            print(f"   신뢰도: {result.confidence:.2f}")

            return result

        except Exception as e:
            print(f"❌ 분류 실패: {e}")
            return None

    async def batch_classify(self, directory: str, user_id: str = None):
        """디렉토리 내 모든 파일 분류

        MCP가 워크스페이스 전체를 분류할 때 사용
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
    """CLI 실행 예제"""
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
    asyncio.run(main())
