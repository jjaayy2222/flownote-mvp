# streamlit/test_ui2.py
"""
FlowNote 통합 UI - 파일 업로드 → LangChain 분류 → 메타데이터 표시
"""

import os
import sys
from pathlib import Path

# 프로젝트 루트 경로 추가 (중요!!!)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

# 두 번째: Streamlit + 환경변수 로드
import streamlit as st

# 로컬에서는 .env 로드
load_dotenv()

# 세 번째: 배포 환경에서는 Streamlit Secrets 로드
try:
    if hasattr(st, "secrets") and len(st.secrets) > 0:
        for key in [
            "EMBEDDING_API_KEY",
            "EMBEDDING_BASE_URL",
            "EMBEDDING_MODEL",
            "EMBEDDING_LARGE_API_KEY",
            "EMBEDDING_LARGE_BASE_URL",
            "EMBEDDING_LARGE_MODEL",
            "GPT4O_API_KEY",
            "GPT4O_BASE_URL",
            "GPT4O_MODEL",
            "GPT4O_MINI_API_KEY",
            "GPT4O_MINI_BASE_URL",
            "GPT4O_MINI_MODEL",
            "GPT41_API_KEY",
            "GPT41_BASE_URL",
            "GPT41_MODEL",
        ]:
            if key in st.secrets:
                os.environ[key] = st.secrets[key]
except:
    pass


import json
from datetime import datetime

import numpy as np

from backend.chunking import TextChunker

# 네 번째: 다음 임포트
from backend.classifier.para_agent_wrapper import run_para_agent_sync
from backend.database.connection import DatabaseConnection
from backend.database.metadata_schema import ClassificationMetadataExtender
from backend.embedding import EmbeddingGenerator
from backend.export import MarkdownExporter
from backend.faiss_search import FAISSRetriever
from backend.metadata import FileMetadata
from backend.search_history import SearchHistory
from backend.utils import load_pdf

# 페이지 설정
st.set_page_config(
    page_title="FlowNote",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 커스텀 CSS - 애플 스타일
st.markdown(
    """
<style>
    /* 전체 배경 */
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    }
    
    /* 헤더 스타일 */
    h1 {
        color: #1d1d1f;
        font-weight: 600;
        letter-spacing: -0.5px;
    }
    
    /* 카드 스타일 */
    .upload-card, .search-card, .result-card {
        background: white;
        border-radius: 16px;
        padding: 24px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.07);
        margin: 16px 0;
    }
    
    /* 버튼 스타일 */
    .stButton>button {
        border-radius: 12px;
        font-weight: 500;
        border: none;
        transition: all 0.3s ease;
    }
    
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 12px rgba(0, 0, 0, 0.1);
    }
    
    /* 탭 스타일 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        border-radius: 12px 12px 0 0;
        padding: 12px 24px;
        font-weight: 500;
    }
    
    /* 메트릭 카드 */
    [data-testid="stMetricValue"] {
        font-size: 28px;
        font-weight: 600;
    }
    
    /* 입력 필드 */
    .stTextInput>div>div>input {
        border-radius: 12px;
        border: 2px solid #e5e5e7;
    }
</style>
""",
    unsafe_allow_html=True,
)

# 세션 상태 초기화
if "classification_history" not in st.session_state:
    st.session_state.classification_history = []

if "db_extender" not in st.session_state:
    st.session_state.db_extender = ClassificationMetadataExtender()

if "faiss_retriever" not in st.session_state:
    st.session_state.faiss_retriever = None

if "file_metadata" not in st.session_state:
    st.session_state.file_metadata = FileMetadata()

if "search_history" not in st.session_state:
    st.session_state.search_history = SearchHistory()

if "last_search_results" not in st.session_state:
    st.session_state.last_search_results = None

if "last_search_query" not in st.session_state:
    st.session_state.last_search_query = None

# 타이틀
st.title("📚 FlowNote")
st.markdown("**AI 기반 문서 검색 & 자동 분류 시스템**")

# 사이드바
with st.sidebar:
    st.header("📊 시스템 정보")

    # 파일 통계
    if st.session_state.file_metadata.metadata:
        stats = st.session_state.file_metadata.get_statistics()
        st.metric("📁 전체 파일", stats["total_files"])
        st.metric("📦 전체 청크", stats["total_chunks"])
        st.metric("💾 총 크기", f"{stats['total_size_mb']} MB")

    st.divider()

    # 분류 히스토리
    st.subheader("🤖 분류 히스토리")
    if st.session_state.classification_history:
        for item in st.session_state.classification_history[-5:]:
            with st.expander(f"📄 {item['filename'][:20]}..."):
                st.write(f"**카테고리**: {item['category']}")
                st.write(f"**신뢰도**: {item['confidence']:.0%}")
                st.caption(item["timestamp"])
    else:
        st.info("아직 분류된 파일이 없습니다")

    st.divider()

    # 검색 히스토리
    st.subheader("🔍 최근 검색")
    history = st.session_state.search_history.get_recent_searches(3)
    if history:
        for item in history:
            st.caption(f"🔎 {item['query']}")
            st.caption(f"   {item['results_count']}개 결과")
    else:
        st.info("검색 기록이 없습니다")

# 메인 탭
tab1, tab2, tab3 = st.tabs(
    ["🏠 홈 - 검색 & 업로드", "🤖 자동 분류", "📊 통계 대시보드"]
)

# ============================================================================
# TAB 1: 홈 - 통합 검색 & 업로드
# ============================================================================
with tab1:
    col1, col2 = st.columns([1, 1])

    # 왼쪽: 파일 업로드
    with col1:
        st.markdown("### 📤 파일 업로드")
        st.markdown('<div class="upload-card">', unsafe_allow_html=True)

        uploaded_files = st.file_uploader(
            "문서를 업로드하세요 (PDF, TXT, MD)",
            type=["pdf", "txt", "md"],
            accept_multiple_files=True,
            help="여러 파일을 동시에 업로드할 수 있습니다",
        )

        if uploaded_files:
            st.success(f"✅ {len(uploaded_files)}개 파일 선택됨")

            if st.button("🚀 파일 처리 시작", type="primary", width="stretch"):
                doc_list = []
                progress_bar = st.progress(0)
                status_text = st.empty()

                # 파일 읽기
                for i, uploaded_file in enumerate(uploaded_files):
                    status_text.text(f"📄 {uploaded_file.name} 처리 중...")
                    try:
                        if uploaded_file.type == "application/pdf":
                            content = load_pdf(uploaded_file)
                        else:
                            content = uploaded_file.read().decode("utf-8")

                        doc_list.append(
                            {
                                "name": uploaded_file.name,
                                "content": content,
                                "size": uploaded_file.size,
                                "type": uploaded_file.type,
                            }
                        )
                    except Exception as e:
                        st.error(f"❌ {uploaded_file.name}: {str(e)}")

                    progress_bar.progress((i + 1) / len(uploaded_files))

                if doc_list:
                    status_text.text("🔮 임베딩 생성 중...")

                    # 청킹
                    chunker = TextChunker()
                    all_chunks = []
                    chunk_metadata = []

                    for doc in doc_list:
                        chunks = chunker.chunk_text(doc["content"])
                        all_chunks.extend(chunks)
                        for chunk in chunks:
                            chunk_metadata.append(
                                {"filename": doc["name"], "file_type": doc["type"]}
                            )

                    # 임베딩
                    embedder = EmbeddingGenerator()
                    result = embedder.generate_embeddings(all_chunks)
                    embeddings_array = np.array(result["embeddings"])

                    # FAISS 인덱스
                    documents = []
                    for chunk, meta in zip(all_chunks, chunk_metadata):
                        documents.append({"content": chunk, "metadata": meta})

                    retriever = FAISSRetriever(dimension=embeddings_array.shape[1])
                    retriever.add_documents(embeddings_array, documents)
                    st.session_state.faiss_retriever = retriever

                    # 메타데이터 저장
                    for doc in doc_list:
                        count = sum(
                            1 for m in chunk_metadata if m["filename"] == doc["name"]
                        )
                        st.session_state.file_metadata.add_file(
                            file_name=doc["name"],
                            file_size=doc["size"],
                            chunk_count=count,
                            embedding_dim=embeddings_array.shape[1],
                        )

                    status_text.empty()
                    progress_bar.empty()
                    st.success(
                        f"✅ {len(doc_list)}개 파일, {len(all_chunks)}개 청크 처리 완료!"
                    )

        st.markdown("</div>", unsafe_allow_html=True)

    # 오른쪽: 검색
    with col2:
        st.markdown("### 🔍 문서 검색")
        st.markdown('<div class="search-card">', unsafe_allow_html=True)

        if st.session_state.faiss_retriever:
            query = st.text_input(
                "검색어를 입력하세요",
                placeholder="예: FlowNote 사용법",
                help="자연어로 질문하거나 키워드를 입력하세요",
            )

            col_k, col_btn = st.columns([1, 2])
            with col_k:
                k = st.slider("결과 개수", 1, 10, 3)

            with col_btn:
                search_button = st.button("🔎 검색", type="primary", width="stretch")

            if query and search_button:
                with st.spinner("검색 중..."):
                    results = st.session_state.faiss_retriever.search(query, k=k)
                    st.session_state.search_history.add_search(
                        query=query, results_count=len(results)
                    )
                    st.session_state.last_search_results = results
                    st.session_state.last_search_query = query

                st.success(f"✅ {len(results)}개 결과 발견!")
        else:
            st.info("💡 먼저 문서를 업로드해주세요")

        st.markdown("</div>", unsafe_allow_html=True)

    # 검색 결과 표시
    if st.session_state.last_search_results:
        st.divider()
        st.markdown("### 📊 검색 결과")

        for i, result in enumerate(st.session_state.last_search_results, 1):
            with st.expander(
                f"**결과 #{i}** | {result['metadata']['filename']} | 유사도: {result['score']:.2%}",
                expanded=(i == 1),
            ):
                st.markdown(result["content"])
                st.caption(f"파일: {result['metadata']['filename']}")

        # 결과 저장
        col_export, col_clear = st.columns([3, 1])
        with col_export:
            if st.button("💾 검색 결과 MD로 저장", width="stretch"):
                exporter = MarkdownExporter()
                md_content = exporter.export_search_results(
                    query=st.session_state.last_search_query,
                    results=st.session_state.last_search_results,
                )
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"flownote_search_{timestamp}.md"
                st.download_button(
                    label="⬇️ 다운로드",
                    data=md_content,
                    file_name=filename,
                    mime="text/markdown",
                    width="stretch",
                )

# ============================================================================
# TAB 2: 자동 분류
# ============================================================================
with tab2:
    st.header("🤖 AI 자동 분류")

    uploaded_file = st.file_uploader(
        "분류할 파일을 업로드하세요",
        type=["pdf", "txt", "md"],
        help="PDF, TXT, MD 파일을 지원합니다",
    )

    if uploaded_file:
        # 파일 정보 표시
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📄 파일명", uploaded_file.name)
        with col2:
            st.metric("📦 크기", f"{uploaded_file.size / 1024:.2f} KB")
        with col3:
            st.metric("🏷️ 타입", uploaded_file.type.split("/")[-1].upper())

        # 분류 버튼
        if st.button("🚀 분류 시작", type="primary", width="stretch"):
            with st.spinner("🤖 AI가 파일을 분석하고 있습니다..."):
                try:
                    # 1. 파일 읽기
                    if uploaded_file.type == "application/pdf":
                        text = load_pdf(uploaded_file)
                    else:
                        text = uploaded_file.read().decode("utf-8")

                    # 2. 메타데이터 구성
                    metadata = {
                        "filename": uploaded_file.name,
                        "file_size": uploaded_file.size,
                        "file_type": uploaded_file.type,
                        "uploaded_at": datetime.now().isoformat(),
                    }

                    # 3. LangChain + LangGraph 기반 분류
                    classification_result = run_para_agent_sync(
                        text=text[:2000], metadata=metadata
                    )

                    # 4. 데이터베이스 저장
                    file_id = st.session_state.db_extender.save_classification_result(
                        result=classification_result, filename=uploaded_file.name
                    )

                    # 5. 히스토리 저장
                    history_item = {
                        "filename": uploaded_file.name,
                        "category": classification_result.get("category", "Unknown"),
                        "confidence": classification_result.get("confidence", 0),
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "file_id": file_id,
                    }
                    st.session_state.classification_history.append(history_item)

                    st.success("✅ 분류 완료!")

                    # 6. 결과 표시
                    st.markdown("---")
                    st.subheader("📊 분류 결과")

                    # 카테고리 아이콘
                    category_icons = {
                        "Projects": "🚀",
                        "Areas": "🎯",
                        "Resources": "📚",
                        "Archives": "📦",
                    }

                    category = classification_result.get("category", "Unknown")
                    icon = category_icons.get(category, "❓")

                    # 결과 카드
                    col1, col2 = st.columns([2, 1])

                    with col1:
                        st.markdown(f"### {icon} {category}")
                        st.progress(classification_result.get("confidence", 0))
                        st.caption(
                            f"신뢰도: {classification_result.get('confidence', 0):.0%}"
                        )

                    with col2:
                        if classification_result.get("conflict_detected", False):
                            st.warning("⚠️ 충돌 감지됨")
                        else:
                            st.success("✅ 명확한 분류")

                        if classification_result.get("requires_review", False):
                            st.info("👀 검토 필요")

                    # 상세 정보
                    with st.expander("📝 분류 근거", expanded=True):
                        st.markdown(classification_result.get("reasoning", "정보 없음"))

                    with st.expander("🔑 키워드 태그"):
                        tags = classification_result.get("keyword_tags", [])
                        if tags:
                            st.write(", ".join([f"`{tag}`" for tag in tags[:10]]))
                        else:
                            st.caption("키워드 없음")

                    # 메타데이터 표시
                    with st.expander("📋 메타데이터"):
                        st.json(
                            {
                                "filename": uploaded_file.name,
                                "file_size_kb": f"{uploaded_file.size / 1024:.2f}",
                                "file_type": uploaded_file.type,
                                "classified_at": datetime.now().isoformat(),
                                "file_id": file_id,
                            }
                        )

                except Exception as e:
                    st.error(f"❌ 분류 실패: {str(e)}")

# ============================================================================
# TAB 3: 통계 대시보드
# ============================================================================
with tab3:
    st.header("📊 통계 대시보드")

    # 상단 KPI
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        total_files = len(st.session_state.classification_history)
        st.metric("📁 분류된 파일", total_files)

    with col2:
        if st.session_state.faiss_retriever:
            st.metric("🔍 인덱스 크기", st.session_state.faiss_retriever.size())
        else:
            st.metric("🔍 인덱스 크기", 0)

    with col3:
        search_count = len(st.session_state.search_history.get_all_searches())
        st.metric("🔎 총 검색", search_count)

    with col4:
        if st.session_state.classification_history:
            avg_conf = sum(
                item["confidence"] for item in st.session_state.classification_history
            ) / len(st.session_state.classification_history)
            st.metric("⭐ 평균 신뢰도", f"{avg_conf:.0%}")
        else:
            st.metric("⭐ 평균 신뢰도", "0%")

    st.divider()

    # 카테고리별 통계
    if st.session_state.classification_history:
        from collections import Counter

        col1, col2 = st.columns([1, 1])

        with col1:
            st.subheader("📊 카테고리 분포")
            categories = [
                item["category"] for item in st.session_state.classification_history
            ]
            category_counts = Counter(categories)

            for category, count in category_counts.most_common():
                icon = {
                    "Projects": "🚀",
                    "Areas": "🎯",
                    "Resources": "📚",
                    "Archives": "📦",
                }.get(category, "❓")
                st.metric(f"{icon} {category}", count)

        with col2:
            st.subheader("📈 최근 활동")
            for item in st.session_state.classification_history[-5:]:
                with st.container():
                    st.markdown(f"**{item['filename']}**")
                    st.caption(f"{item['category']} | {item['timestamp']}")
                    st.divider()
    else:
        st.info("📊 아직 통계 데이터가 없습니다. TAB 2에서 파일을 분류해보세요!")

# 하단 정보
st.divider()
st.caption("FlowNote v3.2 | LangChain + LangGraph 통합 | Made with ❤️ by Jay")
