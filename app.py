# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# app.py (3rd)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - AI 대화 관리 도구
작성자: Jay Lee
날짜: 2025.10.25
"""

import streamlit as st
from pathlib import Path
from datetime import datetime
import sys

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from backend.chunking import TextChunker
from backend.embedding import EmbeddingGenerator
from backend.faiss_search import FAISSRetriever
from backend.metadata import FileMetadata
from backend.search_history import SearchHistory

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 페이지 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

st.set_page_config(
    page_title="FlowNote MVP",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 초기화
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

if 'retriever' not in st.session_state:
    st.session_state.retriever = FAISSRetriever()

if 'metadata' not in st.session_state:
    st.session_state.metadata = FileMetadata()

if 'history' not in st.session_state:
    st.session_state.history = SearchHistory()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 사이드바
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

with st.sidebar:
    st.title("🤖 FlowNote MVP")
    st.markdown("---")
    
    # 파일 통계
    st.subheader("📊 파일 통계")
    stats = st.session_state.metadata.get_statistics()
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("총 파일", f"{stats['total_files']}개")
        st.metric("총 청크", f"{stats['total_chunks']}개")
    with col2:
        st.metric("총 용량", f"{stats['total_size_mb']} MB")
        st.metric("모델 수", f"{len(stats['models_used'])}개")
    
    st.markdown("---")
    
    # 파일 목록
    st.subheader("📁 파일 목록")
    all_files = st.session_state.metadata.get_all_files()
    
    if all_files:
        for file_id, info in all_files.items():
            with st.expander(f"📄 {info['file_name']}", expanded=False):
                st.write(f"**크기:** {info['file_size_mb']} MB")
                st.write(f"**청크:** {info['chunk_count']}개")
                st.write(f"**모델:** {info['embedding_model']}")
                st.write(f"**업로드:** {info['created_at']}")
    else:
        st.info("파일이 없습니다.")
    
    st.markdown("---")
    
    # 검색 통계
    st.subheader("🔍 검색 통계")
    search_stats = st.session_state.history.get_statistics()
    
    st.metric("총 검색", f"{search_stats['total_searches']}회")
    if search_stats['most_common_query']:
        st.write(f"**자주 검색:** {search_stats['most_common_query']}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 페이지
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

# 탭 생성
tab1, tab2, tab3 = st.tabs(["📤 파일 업로드", "🔍 검색", "📊 히스토리"])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 탭 1: 파일 업로드
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

with tab1:
    st.header("📤 파일 업로드")
    st.write("텍스트 파일을 업로드하면 자동으로 처리됩니다.")
    
    uploaded_file = st.file_uploader(
        "파일 선택",
        type=['txt', 'md'],
        help="텍스트 파일 (txt, md)을 업로드하세요."
    )
    
    if uploaded_file:
        if st.button("🚀 처리 시작", type="primary"):
            with st.spinner("파일 처리 중..."):
                # 1. 파일 저장
                content = uploaded_file.read().decode('utf-8')
                timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                file_path = Path(f"data/uploads/{timestamp}_{uploaded_file.name}")
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding='utf-8')
                
                # 2. 청킹
                chunker = TextChunker()
                chunks = chunker.chunk_text(content)
                
                # 3. 임베딩
                embedder = EmbeddingGenerator()
                embeddings, token_count, cost = embedder.generate_embeddings(chunks)
                
                # 4. FAISS 저장
                st.session_state.retriever.add_documents(chunks, embeddings)
                
                # 5. 메타데이터 저장
                file_id = st.session_state.metadata.add_file(
                    file_name=uploaded_file.name,
                    file_size=uploaded_file.size,
                    chunk_count=len(chunks),
                    embedding_dim=len(embeddings[0])
                )
                
                st.success("✅ 처리 완료!")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("청크 수", f"{len(chunks)}개")
                with col2:
                    st.metric("토큰 수", f"{token_count:,}")
                with col3:
                    st.metric("비용", f"${cost:.6f}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 탭 2: 검색
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

with tab2:
    st.header("🔍 검색")
    
    query = st.text_input(
        "질문을 입력하세요",
        placeholder="예: FlowNote의 주요 기능은?"
    )
    
    col1, col2 = st.columns([3, 1])
    with col1:
        top_k = st.slider("결과 개수", 1, 10, 3)
    with col2:
        search_button = st.button("🔍 검색", type="primary")
    
    if search_button and query:
        with st.spinner("검색 중..."):
            # 검색 수행
            results = st.session_state.retriever.search(query, top_k=top_k)
            
            # 검색 히스토리 저장
            top_results = [r['text'][:100] for r in results[:3]]
            st.session_state.history.add_search(
                query=query,
                results_count=len(results),
                top_results=top_results
            )
            
            # 결과 표시
            st.success(f"✅ {len(results)}개 결과 발견!")
            
            for i, result in enumerate(results, 1):
                with st.expander(f"#{i} - 유사도: {result['score']:.4f}", expanded=(i==1)):
                    st.write(result['text'])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 탭 3: 히스토리
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

with tab3:
    st.header("📊 검색 히스토리")
    
    # 최근 검색 표시
    recent_searches = st.session_state.history.get_recent_searches(limit=10)
    
    if recent_searches:
        for search in recent_searches:
            with st.expander(
                f"🔍 {search['query']} ({search['created_at']})",
                expanded=False
            ):
                st.write(f"**결과 수:** {search['results_count']}개")
                if search['top_results']:
                    st.write("**상위 결과:**")
                    for i, result in enumerate(search['top_results'], 1):
                        st.write(f"{i}. {result}")
    else:
        st.info("검색 기록이 없습니다.")
    
    # 히스토리 삭제
    st.markdown("---")
    if st.button("🗑️ 히스토리 전체 삭제", type="secondary"):
        st.session_state.history.clear_all()
        st.success("✅ 히스토리가 삭제되었습니다!")
        st.rerun()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# Footer
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray;'>
        FlowNote MVP v1.0 | Made with ❤️ by Jay
    </div>
    """,
    unsafe_allow_html=True
)



"""result



"""