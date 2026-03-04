# backend/services/chat_service.py

import json
import logging
import asyncio
from typing import AsyncGenerator, List, Optional
from functools import lru_cache

from langchain_core.documents import Document
from langchain_core.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain_core.retrievers import BaseRetriever
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain

from backend.services.hybrid_search_service import (
    HybridSearchService,
    get_hybrid_search_service,
)
from backend.services.onboarding_service import OnboardingService

logger = logging.getLogger(__name__)


class HybridSearchLangChainRetriever(BaseRetriever):
    """HybridSearchService를 LangChain Retriever로 래핑"""

    service: HybridSearchService
    k: int = 5
    alpha: float = 0.5

    model_config = {"arbitrary_types_allowed": True}

    def _get_relevant_documents(
        self, query: str, *, run_manager=None
    ) -> List[Document]:
        """비동기 호출(aget) 전용으로, 동기 호출은 지원하지 않습니다."""
        raise NotImplementedError(
            "This retriever only supports asynchronous execution (_aget_relevant_documents)."
        )

    async def _aget_relevant_documents(
        self, query: str, *, run_manager=None
    ) -> List[Document]:
        """비동기 하이브리드 검색 실행하여 LangChain Document 객체로 변환"""
        result = await self.service.search(query=query, k=self.k, alpha=self.alpha)
        docs = []
        for res in result.results:
            content = res.get("content", "")
            # 원본 검색 결과의 metadata 훼손을 방지하기 위해 얕은 복사 후 조작
            metadata = dict(res.get("metadata", {}))
            metadata["id"] = res.get("id", "")
            metadata["score"] = res.get("score", 0.0)
            docs.append(Document(page_content=content, metadata=metadata))
        return docs


class ChatService:
    def __init__(
        self,
        hybrid_search_service: HybridSearchService,
        onboarding_service: OnboardingService,
    ):
        self.hybrid_search_service = hybrid_search_service
        self.onboarding_service = onboarding_service

    def _get_streaming_llm(self):
        """스트리밍용 ChatOpenAI 객체 생성"""
        from langchain_openai import ChatOpenAI
        import os

        return ChatOpenAI(
            model=os.getenv("GPT4O_MODEL", "gpt-4o"), streaming=True, temperature=0.3
        )

    def _get_user_context_prompt_text(self, user_id: str) -> str:
        """온보딩 데이터를 기반으로 사용자 맞춤형 시스템 프롬프트 문구 생성"""
        try:
            status = self.onboarding_service.get_user_status(user_id)
            if status.get("status") == "success" and status.get("is_completed"):
                occupation = status.get("occupation", "알 수 없음")
                areas = ", ".join(status.get("areas", []))
                return (
                    f"You are assisting a user who works as a '{occupation}' and is interested in the following areas: {areas}. "
                    "Tailor your response to be suitable and helpful for someone with this background."
                )
        except Exception as e:
            logger.warning(f"Failed to fetch onboarding status for user {user_id}: {e}")

        return "You are a helpful and expert AI assistant."

    @staticmethod
    def _format_sse_event(event_type: str, **kwargs) -> str:
        """SSE 규격에 맞게 이벤트를 포맷팅하는 헬퍼 함수"""
        payload = {"type": event_type}
        payload.update(kwargs)
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def stream_chat(
        self,
        query: str,
        user_id: str,
        k: int = 5,
        alpha: float = 0.5,
    ) -> AsyncGenerator[str, None]:
        """질의를 받아 RAG 체인을 실행하고 SSE 규격에 맞게 결과 청크를 반환하는 비동기 제너레이터"""
        logger.info(f"Stream chat started for user {user_id}")

        llm = self._get_streaming_llm()

        # 1. Custom Retriever 구성
        retriever = HybridSearchLangChainRetriever(
            service=self.hybrid_search_service, k=k, alpha=alpha
        )

        # 2. 사용자 상황에 맞춘 시스템 프롬프트 템플릿 작성
        user_context_msg = self._get_user_context_prompt_text(user_id)

        system_template = f"""{user_context_msg}

Answer the user's question clearly and accurately, using ONLY the context provided below.
If you cannot answer the question using the context, state "주어진 문서 내용에서는 답변을 찾을 수 없습니다." and do not guess.
Do not mention the words "context" or "provided text" explicitly in your final answer, just answer the question directly.

Context: 
{{context}}
"""
        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(system_template),
                HumanMessagePromptTemplate.from_template("{input}"),
            ]
        )

        # 3. 문서 결합 체인 및 RAG 검색 체인 생성
        document_chain = create_stuff_documents_chain(llm, prompt)
        retrieval_chain = create_retrieval_chain(retriever, document_chain)

        # 4. Langchain Runnable Streaming 실행 (v2 Events API 사용으로 진짜 토큰 단위 스트리밍 달성)
        sources_emitted = False
        is_cancelled = False

        try:
            async for event in retrieval_chain.astream_events(
                {"input": query}, version="v2"
            ):
                kind = event["event"]

                # 검색기 종료 시점 (컨텍스트 로드 완료)에 소스 전송
                if kind == "on_retriever_end" and not sources_emitted:
                    docs = event["data"].get("output", [])
                    if docs and isinstance(docs, list):
                        sources = []
                        for doc in docs:
                            if hasattr(doc, "metadata"):
                                sources.append(
                                    {
                                        "id": doc.metadata.get("id", ""),
                                        "score": doc.metadata.get("score", 0.0),
                                    }
                                )
                        # Source Documents 메타데이터를 클라이언트로 1회만 전송
                        yield self._format_sse_event("sources", data=sources)
                        sources_emitted = True

                # 채팅 모델에서 스트리밍되는 실제 텍스트 토큰
                elif kind == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    if chunk and getattr(chunk, "content", None):
                        yield self._format_sse_event("token", data=chunk.content)

        except asyncio.CancelledError:
            # 클라이언트 연결 끊김/취소 시 조기 종료 시그널 마킹 후 예외를 다시 던짐
            is_cancelled = True
            logger.info("Chat stream cancelled by user.")
            raise
        except Exception as e:
            # 서버 측 상세 에러 기록 (내부 로깅)
            logger.exception("Error during streaming RAG chat")
            # 클라이언트 측에는 일반(Generic) 메시지 전송
            yield self._format_sse_event(
                "error",
                message="서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
            )

        # GeneratorExit/CancelledError 중에는 yield를 호출하면 안되므로 정상/내부오류 발생 시에만 DONE 방출
        if not is_cancelled:
            yield "data: [DONE]\n\n"


@lru_cache(maxsize=None)
def get_chat_service() -> ChatService:
    return ChatService(
        hybrid_search_service=get_hybrid_search_service(),
        onboarding_service=OnboardingService(),
    )
