import asyncio
import logging
from backend.services.chat_service import get_chat_service

logging.basicConfig(level=logging.ERROR)

async def main():
    service = get_chat_service()
    try:
        gen = service.stream_chat(query="지금까지의 메모를 바탕으로 내 직업과 주요 관심사가 뭔지 요약해줘.", user_id="test_user_123", k=3, alpha=0.5)
        async for chunk in gen:
            pass # just consume to catch error logger
    except Exception as e:
        pass

if __name__ == "__main__":
    asyncio.run(main())
