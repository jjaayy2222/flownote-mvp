import json
import logging
import asyncio
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional
from functools import lru_cache

from langchain_core.callbacks.manager import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain_core.retrievers import BaseRetriever

from backend.services.hybrid_search_service import (
    HybridSearchService,
    get_hybrid_search_service,
)
from backend.services.onboarding_service import OnboardingService
from backend.services.chat_history_service import (
    ChatHistoryService,
    get_chat_history_service,
)
from backend.api.models import ChatMessage

logger = logging.getLogger(__name__)

# [Engineering Decision] SSE 페이로드 크기 및 성능 최적화를 위한 상수
MAX_SOURCE_PAGE_CONTENT_LEN = 500


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

    async def aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager: Optional[CallbackManagerForRetrieverRun] = None,
        **kwargs: Any,
    ) -> List[Document]:
        """Provides backward-compatibility for traditional BaseRetriever interface."""
        if run_manager:
            # 기존 제공된 config 딕셔너리를 무조건 덮어쓰지 않고 추출(Merge)
            config = kwargs.pop("config", {}) or {}
            # run_manager 콜백을 병합하면서, 다른 config 키(태그, 메타데이터 등)를 보존
            config["callbacks"] = run_manager.get_child()
            kwargs["config"] = config
        return await self.ainvoke(query, **kwargs)


class ChatService:
    def __init__(
        self,
        hybrid_search_service: HybridSearchService,
        onboarding_service: OnboardingService,
        chat_history_service: ChatHistoryService,
    ):
        self.hybrid_search_service = hybrid_search_service
        self.onboarding_service = onboarding_service
        self.chat_history_service = chat_history_service

        import os

        # 런타임마다 읽지 않고 서비스 초기화 시점에 한 번만 읽고 검증(Fail Fast)
        try:
            raw_docs = os.getenv("RAG_MAX_DOCS", "10")
            raw_chars = os.getenv("RAG_MAX_DOC_CHARS", "2000")
            raw_total = os.getenv("RAG_MAX_TOTAL_CHARS", "16000")

            self.rag_max_docs = int(raw_docs)
            self.rag_max_doc_chars = int(raw_chars)
            self.rag_max_total_chars = int(raw_total)

            if any(
                val < 0
                for val in (
                    self.rag_max_docs,
                    self.rag_max_doc_chars,
                    self.rag_max_total_chars,
                )
            ):
                raise ValueError(
                    f"RAG bounds must be non-negative. "
                    f"Parsed values: docs={self.rag_max_docs}, chars={self.rag_max_doc_chars}, total={self.rag_max_total_chars}"
                )
        except ValueError as e:
            # 설정 무결성을 위반했으므로 구체적인 값을 로그에 담아 명확히 에러 전파(Fail-Fast)
            logger.error(
                f"Invalid RAG configuration detected. "
                f"Env values were -> RAG_MAX_DOCS='{raw_docs}', "
                f"RAG_MAX_DOC_CHARS='{raw_chars}', "
                f"RAG_MAX_TOTAL_CHARS='{raw_total}'. "
                f"Detail: {e}. Raising exception to fail fast."
            )
            raise

    def _get_streaming_llm(self):
        """스트리밍용 ChatOpenAI 객체 생성"""
        return self._get_llm(streaming=True)

    def _get_llm(self, streaming: bool = False):
        """ChatOpenAI 객체 생성 (기본값: non-streaming)"""
        from langchain_openai import ChatOpenAI
        import os

        # 기본 OPENAI_API_KEY가 없는 환경이므로 .env의 커스텀 환경변수를 명시적으로 주입
        # GPT-4o-mini를 1순위로, GPT-4o 등 다른 모델을 fallback으로 사용
        api_key = (
            os.getenv("GPT4O_MINI_API_KEY")
            or os.getenv("GPT4O_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        if not api_key:
            raise ValueError(
                "OpenAI API key is missing. Please set GPT4O_MINI_API_KEY, GPT4O_API_KEY, or OPENAI_API_KEY in your environment variables."
            )

        base_url = (
            os.getenv("GPT4O_MINI_BASE_URL")
            or os.getenv("GPT4O_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
        )
        model = (
            os.getenv("GPT4O_MINI_MODEL") or os.getenv("GPT4O_MODEL") or "gpt-4o-mini"
        )

        return ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model,
            streaming=streaming,
            temperature=0.3,
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

    def _mask_pii(self, text: Optional[str]) -> str:
        """
        개인정보(PII) 마스킹 가드레일 (이메일, 전화번호 등)

        [Engineering Decision]
        - 스트리밍 토큰 단위 마스킹은 문맥 단절로 리소스가 많이 들 수 있으므로,
        - 소스 문서 내용(Full Text)과 최종 저장 시점(User/Assistant)에 적용하는 것을 1순위로 합니다.
        """
        if not text:
            return ""

        # 1. 이메일: abc@def.com -> a***@def.com
        text = re.sub(
            r"([a-zA-Z0-9_.+-]+)@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)",
            lambda m: m.group(1)[0] + "***@" + m.group(2),
            text,
        )
        # 2. 전화번호 (KR): 010-1234-5678 -> 010-****-5678
        text = re.sub(r"(\d{2,3})-(\d{3,4})-(\d{4})", r"\1-****-\3", text)

        return text

    # ------------------------------------------------------------------
    # [Refinement] 검색 결과 처리 및 성능 로깅 헬퍼
    # ------------------------------------------------------------------
    def _dedupe_and_build_sources(
        self, source_docs: List[Document]
    ) -> tuple[List[Document], List[Dict[str, Any]]]:
        """
        소스 중복 제거 및 SSE 전송용 페이로드 생성.

        [Consistency] UI 노출 문서와 LLM 컨텍스트 문서를 100% 일치시킵니다.
        """
        seen_sources: set[str] = set()
        deduped_docs: List[Document] = []
        payload: List[Dict[str, Any]] = []

        for doc in source_docs:
            # source가 없으면 id를 fallback으로 사용 (리뷰 반영)
            # 메타데이터 타입 불일치 방지를 위해 명시적 문자열 변환
            source_path = str(
                doc.metadata.get("source") or doc.metadata.get("id") or "unknown"
            )
            if source_path in seen_sources:
                continue

            seen_sources.add(source_path)
            deduped_docs.append(doc)

            payload.append(
                {
                    "id": doc.metadata.get("id", ""),
                    "score": doc.metadata.get("score", 0.0),
                    "source": source_path,
                    "title": (
                        source_path.split("/")[-1]
                        if "/" in source_path
                        else source_path
                    ),
                    "page_content": self._mask_pii(doc.page_content)[
                        :MAX_SOURCE_PAGE_CONTENT_LEN
                    ],
                }
            )

        return deduped_docs, payload

    def _log_ttft_once(
        self,
        *,
        start_time: float,
        rephrase_duration: float,
        search_duration: float,
        user_id: str,
    ) -> float:
        """첫 번째 토큰 발생 시 성능 지표 기록"""
        ttft = time.perf_counter() - start_time
        logger.info(
            f"[Performance] TTFT recorded for user {user_id}",
            extra={
                "ttft": ttft,
                "rephrase_duration": rephrase_duration,
                "search_duration": search_duration,
                "user_id": user_id,
            },
        )
        return ttft

    async def _rephrase_query(self, query: str, history: List[ChatMessage]) -> str:
        """이전 대화 맥락을 기반으로 질의 재구성 (Query Rewriting)"""
        if not history:
            return query

        from langchain_core.output_parsers import StringOutputParser

        # 최근 5개 정도의 대화만 맥락으로 사용
        context_history = "\n".join([f"{m.role}: {m.content}" for m in history[-5:]])

        rephrase_template = """Given the following conversation history and a follow-up question, rephrase the follow-up question to be a standalone question that can be understood without the conversation history.
If the follow-up question is already standalone, return it exactly as is.

Chat History:
{history}

Follow-up Question: {query}
Standalone Question:"""

        rephrase_prompt = ChatPromptTemplate.from_template(rephrase_template)
        # 쿼리 재구성 작업은 스트리밍이 필요 없으므로 일반 LLM 사용
        llm = self._get_llm(streaming=False)

        chain = rephrase_prompt | llm | StringOutputParser()

        try:
            standalone_query = await chain.ainvoke(
                {"history": context_history, "query": query}
            )
            logger.info(
                "Rephrased query",
                extra={"original": query, "rephrased": standalone_query},
            )
            return standalone_query.strip()
        except Exception as e:
            logger.warning(
                "Query rephrasing failed", extra={"query": query, "error": str(e)}
            )
            return query

    @staticmethod
    def _format_sse_event(event_type: str, **kwargs) -> str:
        """SSE 규격에 맞게 이벤트를 포맷팅하는 헬퍼 함수"""
        if event_type == "done":
            return "data: [DONE]\n\n"

        payload = {"type": event_type}
        payload.update(kwargs)
        # JSON 직렬화 불가 객체(UUID, datetime 등) 방어를 위해 default=str 파라미터 적용
        return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"

    async def stream_chat(
        self,
        query: str,
        user_id: str,
        session_id: Optional[str] = None,
        k: int = 5,
        alpha: float = 0.5,
    ) -> AsyncGenerator[str, None]:
        """질의를 받아 RAG 체인을 실행하고 SSE 규격에 맞게 결과 청크를 반환하는 비동기 제너레이터"""
        start_time = time.perf_counter()
        logger.info(f"Stream chat started for user {user_id}")

        # 0. 히스토리 로드 및 질의 재구성
        history: List[ChatMessage] = []
        effective_query = query
        rephrase_duration = 0.0

        if session_id:
            history = await self.chat_history_service.get_history(session_id)
            if history:
                rephrase_start = time.perf_counter()
                effective_query = await self._rephrase_query(query, history)
                rephrase_duration = time.perf_counter() - rephrase_start

        # 1. Custom Retriever 구성
        retriever = HybridSearchLangChainRetriever(
            service=self.hybrid_search_service, k=k, alpha=alpha
        )

        # 4. Streaming 실행 (astream_events v2 사용)
        is_cancelled = False
        full_content = ""
        ttft_recorded = False

        try:
            # 1.5. 검색 실행 (재구성된 쿼리 사용)
            search_start = time.perf_counter()
            source_docs: List[Document] = await retriever.aget_relevant_documents(
                effective_query
            )
            search_duration = time.perf_counter() - search_start

            # 2. 사용자 상황에 맞춘 시스템 프롬프트 템플릿 작성
            user_context_msg = self._get_user_context_prompt_text(user_id)

            system_template = f"""{user_context_msg}

Answer the user's question clearly and accurately, using ONLY the context provided below.
If you cannot answer the question using the context, state "주어진 문서 내용에서는 답변을 찾을 수 없습니다." and do not guess.
Do not mention the words "context" or "provided text" explicitly in your final answer, just answer the question directly.

Context: 
{{context}}
"""
            prompt_messages = [
                SystemMessagePromptTemplate.from_template(system_template),
            ]
            prompt_messages.append(HumanMessagePromptTemplate.from_template("{input}"))
            prompt = ChatPromptTemplate.from_messages(prompt_messages)

            # 3. 단일 책임 RAG 파이프라인
            def format_docs(docs: List[Document]) -> str:
                """Format retrieved documents securely into a bounded-length context string."""
                limited_docs = docs[: self.rag_max_docs]
                contents: List[str] = []
                total_length = 0

                for i, doc in enumerate(limited_docs, 1):
                    content = doc.page_content or ""
                    header = f"--- Document {i} ---"

                    doc_suffix = "...(truncated)"
                    if len(content) > self.rag_max_doc_chars:
                        safe_len = max(0, self.rag_max_doc_chars - len(doc_suffix))
                        content = content[:safe_len] + doc_suffix

                    doc_text = f"{header}\n{content}\n"

                    remaining = self.rag_max_total_chars - total_length
                    if remaining <= 0:
                        break

                    if len(doc_text) > remaining:
                        total_limit_suffix = " ...(truncated due to total length limit)"
                        if remaining > len(total_limit_suffix):
                            doc_text = (
                                doc_text[: remaining - len(total_limit_suffix)]
                                + total_limit_suffix
                            )
                        else:
                            doc_text = doc_text[:remaining]

                    contents.append(doc_text)
                    total_length += len(doc_text)

                return "\n\n".join(contents)

            # 3) LLM 초기화 및 파이프라인 구성
            llm = self._get_streaming_llm()
            rag_chain = prompt | llm

            # 4) [Orchestration] 소스 중복 제거 및 페이로드 생성
            deduplicated_source_docs, sources_payload = self._dedupe_and_build_sources(
                source_docs
            )

            if sources_payload:
                yield self._format_sse_event("sources", data=sources_payload)

            # 5) 컨텍스트 주입 및 LLM 스트리밍
            context_str = format_docs(deduplicated_source_docs)
            chain_input = {
                "input": query,
                "context": context_str,
            }

            async for event in rag_chain.astream_events(chain_input, version="v2"):
                kind = event["event"]

                if kind == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    if chunk and getattr(chunk, "content", None):
                        # TTFT(Time To First Token) 기록 및 성능 로깅 (헬퍼 사용)
                        if not ttft_recorded:
                            _ = self._log_ttft_once(
                                start_time=start_time,
                                rephrase_duration=rephrase_duration,
                                search_duration=search_duration,
                                user_id=user_id,
                            )
                            ttft_recorded = True

                        full_content += chunk.content
                        # 스트리밍 토큰은 실시간성을 위해 마스킹 없이 우선 전송
                        yield self._format_sse_event("token", data=chunk.content)

        except asyncio.CancelledError:
            is_cancelled = True
            logger.info("Chat stream cancelled by user.")
            raise
        except Exception as e:
            logger.exception(
                "Error during streaming RAG chat",
                extra={"user_id": user_id, "session_id": session_id},
            )
            yield self._format_sse_event(
                "error",
                message="서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
            )

        if not is_cancelled:
            if session_id and full_content:
                # 저장 시 최종 결과물(질의 및 답변)에 대해 PII 마스킹 적용
                masked_query = self._mask_pii(query)
                masked_content = self._mask_pii(full_content)

                await self.chat_history_service.add_message(
                    session_id, "user", masked_query
                )
                await self.chat_history_service.add_message(
                    session_id, "assistant", masked_content
                )

            yield self._format_sse_event("done")


@lru_cache(maxsize=None)
def get_chat_service() -> ChatService:
    return ChatService(
        hybrid_search_service=get_hybrid_search_service(),
        onboarding_service=OnboardingService(),
        chat_history_service=get_chat_history_service(),
    )
