import asyncio
import logging
from backend.services.chat_service import get_chat_service

logging.basicConfig(level=logging.ERROR)

async def main():
    service = get_chat_service()
    try:
        gen = service.stream_chat(query="hi", user_id="test_user_123", k=3, alpha=0.5)
        async for chunk in gen:
            print(chunk, end="")
    except Exception as e:
        logging.exception(f"Unhandled exception during chat streaming: {e}")

if __name__ == "__main__":
    asyncio.run(main())
