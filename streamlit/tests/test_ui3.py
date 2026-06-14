# streamlit/flownote_ui_v4.py
"""
FlowNote v4.0 - 개선된 랜딩 페이지
- Tab1: 자동 분류 랜딩 페이지
- Tab2: 키워드 검색
- Tab3: Overview (통계)
"""

import os
import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime

import numpy as np
from dotenv import load_dotenv

import streamlit as st

# 환경변수 로드
load_dotenv()

# Streamlit Secrets 동기화
try:
    if hasattr(st, "secrets") and len(st.secrets) > 0:
        for key in [
            "EMBEDDING_API_KEY",
            "EMBEDDING_BASE_URL",
            "EMBEDDING_MODEL",
            "GPT4O_MINI_API_KEY",
            "GPT4O_MINI_BASE_URL",
            "GPT4O_MINI_MODEL",
        ]:
            if key in st.secrets:
                os.environ[key] = st.secrets[key]
except:
    pass

from backend.chunking import TextChunker

# Backend 임포트
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

# 다크 그레이 톤의 애플 스타일 CSS
st.markdown(
    """
<style>
    /* 전체 배경 - 다크 그레이 */
    .stApp {
        background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
    }
    
    /* 헤더 */
    h1, h2, h3 {
        color: #ecf0f1;
        font-weight: 600;
        letter-spacing: -0.5px;
    }
    
    /* 카드 스타일 - 라이트 배경 */
    .card {
        background: rgba(255, 255, 255, 0.95);
        border-radius: 16px;
        padding: 32px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        margin: 24px 0;
        backdrop-filter: blur(10px);
    }
    
    /* 업로드 영역 */
    .upload-area {
        background: white;
        border: 2px dashed #bdc3c7;
        border-radius: 16px;
        padding: 48px;
        text-align: center;
        transition: all 0.3s ease;
    }
    
    .upload-area:hover {
        border-color: #3498db;
        background: #f8f9fa;
    }
    
    /* 버튼 스타일 */
    .stButton>button {
        border-radius: 12px;
        font-weight: 500;
        padding: 12px 32px;
        border: none;
        transition: all 0.3s ease;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
    }
    
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 16px rgba(102, 126, 234, 0.3);
    }
    
    /* 탭 스타일 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: rgba(255, 255, 255, 0.1);
        padding: 8px;
        border-radius: 12px;
    }
    
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 12px 24px;
        color: #ecf0f1;
        font-weight: 500;
    }
    
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background: white;
        color: #2c3e50;
    }
    
    /* 메트릭 카드 */
    [data-testid="stMetricValue"] {
        font-size: 32px;
        font-weight: 700;
        color: #2c3e50;
    }
    
    /* 분류 결과 카드 */
    .result-card {
        background: white;
        border-radius: 16px;
        padding: 32px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
        margin: 16px 0;
    }
    
    /* 카테고리 배지 */
    .category-badge {
        display: inline-block;
        padding: 8px 24px;
        border-radius: 24px;
        font-weight: 600;
        font-size: 18px;
        margin: 16px 0;
    }
    
    .badge-projects { 
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
    }
    .badge-areas { 
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        color: white;
    }
    .badge-resources { 
        background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        color: white;
    }
    .badge-archives { 
        background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
        color: white;
    }
    
    /* 구분선 */
    .divider {
        border-top: 2px solid rgba(255, 255, 255, 0.2);
        margin: 32px 0;
    }
    
    /* 입력 필드 */
    .stTextInput>div>div>input {
        border-radius: 12px;
        border: 2px solid #e5e5e7;
        background: white;
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

if "current_result" not in st.session_state:
    st.session_state.current_result = None

if "uploaded_file_key" not in st.session_state:
    st.session_state.uploaded_file_key = 0

# 타이틀
st.title("📚 FlowNote")
st.markdown("**AI 기반 문서 자동 분류 시스템**")

# 사이드바
with st.sidebar:
    st.header("📊 Overview")

    # 파일 통계
    if st.session_state.file_metadata.metadata:
        stats = st.session_state.file_metadata.get_statistics()
        st.metric("📁 전체 파일", stats["total_files"])
        st.metric("📦 전체 청크", stats["total_chunks"])
        st.metric("💾 총 크기", f"{stats['total_size_mb']} MB")
    else:
        st.info("아직 업로드된 파일이 없습니다")

    st.divider()

    # 분류 히스토리
    st.subheader("🤖 최근 분류")
    if st.session_state.classification_history:
        for item in st.session_state.classification_history[-5:]:
            with st.expander(f"📄 {item['filename'][:20]}..."):
                st.write(f"**카테고리**: {item['category']}")
                st.write(f"**신뢰도**: {item['confidence']:.0%}")
                st.caption(item["timestamp"])
    else:
        st.info("분류 기록이 없습니다")

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
tab1, tab2, tab3 = st.tabs(["🏠 자동 분류", "🔍 키워드 검색", "📊 Overview"])

# ============================================================================
# TAB 1: 자동 분류 랜딩 페이지
# ============================================================================
with tab1:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### 📤 파일 업로드 & 자동 분류")

    # 파일 업로더
    uploaded_file = st.file_uploader(
        "문서를 업로드하면 자동으로 분류됩니다",
        type=["pdf", "txt", "md"],
        help="PDF, TXT, MD 파일 지원",
        key=f"uploader_{st.session_state.uploaded_file_key}",
    )

    st.markdown("</div>", unsafe_allow_html=True)

    # 파일이 업로드되면 자동 분류
    if uploaded_file and st.session_state.current_result is None:
        with st.spinner("🤖 AI가 파일을 분석하고 있습니다..."):
            try:
                # 파일 읽기
                if uploaded_file.type == "application/pdf":
                    text = load_pdf(uploaded_file)
                else:
                    text = uploaded_file.read().decode("utf-8")

                # 메타데이터 구성
                metadata = {
                    "filename": uploaded_file.name,
                    "file_size": uploaded_file.size,
                    "file_type": uploaded_file.type,
                    "uploaded_at": datetime.now().isoformat(),
                }

                # AI 분류 (샘플 텍스트만)
                classification_result = run_para_agent_sync(
                    text=text[:2000], metadata=metadata
                )

                # DB 저장
                file_id = st.session_state.db_extender.save_classification_result(
                    result=classification_result, filename=uploaded_file.name
                )

                # 히스토리 저장
                history_item = {
                    "filename": uploaded_file.name,
                    "category": classification_result.get("category", "Unknown"),
                    "confidence": classification_result.get("confidence", 0),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "file_id": file_id,
                }
                st.session_state.classification_history.append(history_item)
                st.session_state.current_result = classification_result

                st.success("✅ 분류 완료!")

            except Exception as e:
                st.error(f"❌ 분류 실패: {str(e)}")

    # 분류 결과 표시
    if st.session_state.current_result:
        result = st.session_state.current_result

        st.markdown("---")
        st.markdown('<div class="result-card">', unsafe_allow_html=True)

        # 카테고리 아이콘
        category_icons = {
            "Projects": "🚀",
            "Areas": "🎯",
            "Resources": "📚",
            "Archives": "📦",
        }

        category = result.get("category", "Unknown")
        icon = category_icons.get(category, "❓")

        # 카테고리 배지
        badge_class = f"badge-{category.lower()}"
        st.markdown(
            f'<div class="category-badge {badge_class}">{icon} {category}</div>',
            unsafe_allow_html=True,
        )

        # 신뢰도
        confidence = result.get("confidence", 0)
        st.progress(confidence)
        st.caption(f"신뢰도: {confidence:.0%}")

        # 분류 근거
        with st.expander("📝 분류 근거", expanded=True):
            st.markdown(result.get("reasoning", "정보 없음"))

        # 키워드 태그
        with st.expander("🏷️ 키워드 태그"):
            tags = result.get("keyword_tags", [])
            if tags:
                st.write(", ".join([f"`{tag}`" for tag in tags[:10]]))
            else:
                st.caption("키워드 없음")

        st.markdown("</div>", unsafe_allow_html=True)

        # 구분선
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

        # 액션 버튼
        col1, col2 = st.columns(2)

        with col1:
            if st.button(
                "🔍 키워드 검색하기", use_container_width=True, type="primary"
            ):
                st.session_state.current_tab = 2
                st.rerun()

        with col2:
            if st.button("🔄 다른 파일 분류하기", use_container_width=True):
                st.session_state.current_result = None
                st.session_state.uploaded_file_key += 1
                st.rerun()

# ============================================================================
# TAB 2: 키워드 검색
# ============================================================================
with tab2:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### 🔍 문서 검색")

    # 파일 업로드 (검색용)
    uploaded_files_search = st.file_uploader(
        "검색할 문서 업로드",
        type=["pdf", "txt", "md"],
        accept_multiple_files=True,
        help="여러 파일을 동시에 업로드할 수 있습니다",
    )

    if uploaded_files_search and st.button("📄 파일 처리"):
        doc_list = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        # 파일 읽기
        for i, uploaded_file in enumerate(uploaded_files_search):
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

            progress_bar.progress((i + 1) / len(uploaded_files_search))

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
                count = sum(1 for m in chunk_metadata if m["filename"] == doc["name"])
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

    # 검색
    if st.session_state.faiss_retriever:
        st.markdown('<div class="card">', unsafe_allow_html=True)

        query = st.text_input(
            "🔍 검색어를 입력하세요",
            placeholder="예: FlowNote 사용법",
            help="자연어로 질문하거나 키워드를 입력하세요",
        )

        col_k, col_btn = st.columns([1, 2])
        with col_k:
            k = st.slider("결과 개수", 1, 10, 3)

        with col_btn:
            search_button = st.button(
                "🔎 검색", type="primary", use_container_width=True
            )

        if query and search_button:
            with st.spinner("검색 중..."):
                results = st.session_state.faiss_retriever.search(query, k=k)
                st.session_state.search_history.add_search(
                    query=query, results_count=len(results)
                )
                st.session_state.last_search_results = results
                st.session_state.last_search_query = query

            st.success(f"✅ {len(results)}개 결과 발견!")

        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("💡 먼저 문서를 업로드하고 처리해주세요")

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
            if st.button("💾 검색 결과 MD로 저장", use_container_width=True):
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
                    use_container_width=True,
                )

# ============================================================================
# TAB 3: Overview (통계)
# ============================================================================
with tab3:
    st.header("📊 Overview")

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
        st.info("📊 아직 통계 데이터가 없습니다. Tab 1에서 파일을 분류해보세요!")

# 하단 정보
st.divider()
st.caption("FlowNote v4.0 | Made with ❤️ by Jay")
