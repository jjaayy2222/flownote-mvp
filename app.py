# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# app.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - AI 대화 관리 도구
작성자: Jay Lee
날짜: 2025.10.24
"""

import streamlit as st
from pathlib import Path
import sys

# 프로젝트 루트 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from backend.utils import read_file
from backend.chunking import chunk_with_metadata
from backend.embedding import get_embeddings, get_single_embedding
from backend.faiss_search import FAISSRetriever

# 페이지 설정
st.set_page_config(
    page_title="FlowNote MVP",
    page_icon="🔍",
    layout="wide"
)

# 세션 상태 초기화
if 'retriever' not in st.session_state:
    st.session_state.retriever = None
if 'uploaded_files' not in st.session_state:
    st.session_state.uploaded_files = []

# 헤더
st.title("🔍 FlowNote MVP")
st.markdown("**AI 대화를 체계적으로 저장하고 검색하세요!**")

# 사이드바
with st.sidebar:
    st.header("📁 파일 관리")
    
    # 파일 업로드
    uploaded_files = st.file_uploader(
        "Markdown 파일 업로드",
        type=['md', 'txt'],
        accept_multiple_files=True
    )
    
    # 업로드 버튼
    if st.button("📤 업로드 & 처리", type="primary"):
        if uploaded_files:
            with st.spinner("파일 처리 중..."):
                # 검색 엔진 초기화
                if st.session_state.retriever is None:
                    st.session_state.retriever = FAISSRetriever(dimension=1536)
                
                all_chunks = []
                all_embeddings = []
                total_tokens = 0
                total_cost = 0.0
                
                for uploaded_file in uploaded_files:
                    # 파일 읽기
                    content = uploaded_file.read().decode('utf-8')
                    
                    # 청킹
                    chunks = chunk_with_metadata(
                        content,
                        uploaded_file.name,
                        chunk_size=500,
                        chunk_overlap=100
                    )
                    
                    # 임베딩
                    texts = [chunk['text'] for chunk in chunks]
                    embeddings, tokens, cost = get_embeddings(texts, show_progress=False)
                    
                    all_chunks.extend(chunks)
                    all_embeddings.extend(embeddings)
                    total_tokens += tokens
                    total_cost += cost
                
                # FAISS에 추가
                texts_only = [chunk['text'] for chunk in all_chunks]
                st.session_state.retriever.add_documents(
                    texts_only,
                    all_embeddings,
                    all_chunks
                )
                
                st.session_state.uploaded_files.extend([f.name for f in uploaded_files])
                
                st.success(f"✅ {len(uploaded_files)}개 파일 처리 완료!")
                st.info(f"📊 총 {len(all_chunks)}개 청크 생성")
                st.info(f"💰 토큰: {total_tokens:,} | 비용: ${total_cost:.6f}")
        else:
            st.warning("⚠️ 파일을 먼저 선택하세요!")
    
    # 업로드된 파일 목록
    if st.session_state.uploaded_files:
        st.divider()
        st.subheader("📋 업로드된 파일")
        for filename in st.session_state.uploaded_files:
            st.text(f"✓ {filename}")
        
        # 통계
        if st.session_state.retriever:
            stats = st.session_state.retriever.get_stats()
            st.divider()
            st.subheader("📊 통계")
            st.metric("총 문서", stats['total_documents'])
            st.metric("인덱스 크기", stats['index_size'])

# 메인 영역
if st.session_state.retriever is None:
    # 초기 화면
    st.info("👈 사이드바에서 파일을 업로드하세요!")
    
    st.markdown("### 📖 사용 방법")
    st.markdown("""
    1. 사이드바에서 Markdown 파일 업로드
    2. "업로드 & 처리" 버튼 클릭
    3. 검색어 입력하여 검색!
    """)
    
    st.markdown("### ✨ 주요 기능")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("#### 📤 파일 업로드")
        st.markdown("Markdown 파일을 업로드하여 AI 대화를 저장합니다.")
    
    with col2:
        st.markdown("#### 🔍 스마트 검색")
        st.markdown("키워드로 관련 대화를 빠르게 찾을 수 있습니다.")
    
    with col3:
        st.markdown("#### 💾 로컬 저장")
        st.markdown("모든 데이터는 로컬에 안전하게 저장됩니다.")

else:
    # 검색 화면
    st.markdown("### 🔍 검색")
    
    # 검색어 입력
    query = st.text_input(
        "검색어를 입력하세요",
        placeholder="예: Python으로 어떻게 개발하나요?"
    )
    
    # 검색 버튼
    col1, col2 = st.columns([1, 5])
    with col1:
        search_button = st.button("🔍 검색", type="primary")
    with col2:
        top_k = st.slider("결과 개수", 1, 10, 3)
    
    # 검색 실행
    if search_button and query:
        with st.spinner("검색 중..."):
            # 쿼리 임베딩
            query_embedding = get_single_embedding(query)
            
            # 검색
            results = st.session_state.retriever.search(query_embedding, top_k=top_k)
            
            # 결과 표시
            st.divider()
            st.markdown(f"### 📋 검색 결과 ({len(results)}개)")
            
            if results:
                for result in results:
                    with st.expander(
                        f"🏆 {result['rank']}위 | "
                        f"유사도: {result['score']:.2%} | "
                        f"파일: {result.get('filename', 'N/A')}"
                    ):
                        st.markdown(f"**청크 ID:** {result.get('chunk_id', 'N/A')}")
                        st.markdown(f"**위치:** {result.get('start_pos', 'N/A')} - {result.get('end_pos', 'N/A')}")
                        st.divider()
                        st.markdown("**내용:**")
                        st.text(result['text'])
            else:
                st.warning("검색 결과가 없습니다.")
    
    elif search_button:
        st.warning("⚠️ 검색어를 입력하세요!")

# 푸터
st.divider()
st.markdown(
    """
    <div style='text-align: center; color: gray;'>
        FlowNote MVP v0.1.0 | Built with ❤️ by Jay
    </div>
    """,
    unsafe_allow_html=True
)



"""result

    (myenv) ➜  flownote-mvp git:(main) ✗ streamlit run app.py

    You can now view your Streamlit app in your browser.

    Local URL: http://localhost:8501
    Network URL: http://192.168.35.27:8501

    For better performance, install the Watchdog module:

    $ xcode-select --install
    $ pip install watchdog
                
    ✅ 문서 추가 완료!
    - 총 문서 수: 174
    - 인덱스 크기: 174

"""