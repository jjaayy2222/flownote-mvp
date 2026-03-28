# scripts/test_chat_stream.py

import json
import httpx
import asyncio


async def test_streaming_chat():
    url = "http://localhost:8000/api/chat/stream"

    # 미리 준비된 데모 사용자 (온보딩이 완료된 유저 ID 가정)
    payload = {
        "query": "지금까지의 메모를 바탕으로 내 직업과 주요 관심사가 뭔지, 그리고 관련 문서가 있는지 요약해줘.",
        "user_id": "test_user_123",
        "k": 3,
        "alpha": 0.5,
    }

    print("🚀 스트리밍 챗봇 테스트 시작...")
    print("-" * 50)

    # httpx를 사용하여 SSE 스트림 연결
    async with httpx.AsyncClient() as client:
        try:
            async with client.stream(
                "POST", url, json=payload, timeout=30.0
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    # SSE 규격의 빈 줄은 무시
                    if not line.strip():
                        continue

                    # "data: " 프리픽스 제거
                    if line.startswith("data: "):
                        data_str = line[6:]

                        # 종료 시그널
                        if data_str == "[DONE]":
                            print("\n\n✅ [스트리밍 종료 (DONE)]")
                            break

                        try:
                            event = json.loads(data_str)
                            event_type = event.get("type")

                            if event_type == "token":
                                # 토큰을 화면에 줄바꿈 없이 즉각 출력하여 타이핑 효과 확인
                                print(event.get("data", ""), end="", flush=True)

                            elif event_type == "sources":
                                # RAG 검색 출처 데이터 확인
                                print("\n\n📚 [검색된 문서 출처 메타데이터]")
                                print(
                                    json.dumps(
                                        event.get("data", []),
                                        indent=2,
                                        ensure_ascii=False,
                                    )
                                )
                                print("-" * 50)
                                print("💡 챗봇 응답: ", end="")

                            elif event_type == "error":
                                print(f"\n\n❌ [스트리밍 에러]: {event.get('message')}")

                        except json.JSONDecodeError:
                            print(f"[알 수 없는 데이터 수신]: {data_str}")

        except httpx.ConnectError:
            print(
                "🚨 서버 연결 실패! FastAPI 백엔드가 켜져 있는지(localhost:8000) 확인하세요."
            )


if __name__ == "__main__":
    asyncio.run(test_streaming_chat())
