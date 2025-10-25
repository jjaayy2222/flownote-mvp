# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# app.py (파일 목록에 업로드된 파일 추가)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - Streamlit UI
"""

import streamlit as st
from pathlib import Path
from datetime import datetime
import uuid

from backend.chunking import TextChunker
from backend.embedding import EmbeddingGenerator
from backend.faiss_search import FAISSRetriever
from backend.metadata import FileMetadata
from backend.search_history import SearchHistory
from backend.config import EMBEDDING_MODEL

# 페이지 설정
st.set_page_config(
    page_title="FlowNote MVP",
    page_icon="💬",
    layout="wide"
)

# 데이터 디렉토리
DATA_DIR = Path("data")
UPLOADS_DIR = DATA_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Session State 초기화
if 'retriever' not in st.session_state:
    st.session_state.retriever = FAISSRetriever()

if 'metadata' not in st.session_state:
    st.session_state.metadata = FileMetadata()

if 'search_history' not in st.session_state:
    st.session_state.search_history = SearchHistory()


def save_file(uploaded_file) -> Path:
    """파일 저장"""
    file_path = UPLOADS_DIR / uploaded_file.name
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return file_path


def process_uploaded_file(uploaded_file, file_id: str):
    """업로드된 파일 처리 (청킹 → 임베딩 → FAISS)"""
    
    # 1. 파일 읽기
    content = uploaded_file.read().decode('utf-8')
    
    # 2. 청킹
    chunker = TextChunker(chunk_size=500, chunk_overlap=50)
    chunks = chunker.chunk_text(content)
    
    # 3. 임베딩 생성
    generator = EmbeddingGenerator()
    result = generator.generate_embeddings(chunks)
    embeddings = result['embeddings']
    
    # 4. FAISS에 저장
    st.session_state.retriever.add_documents(chunks, embeddings)
    
    # 5. 메타데이터에 기록
    st.session_state.metadata.add_file(
        file_name=uploaded_file.name,
        file_size=uploaded_file.size,
        chunk_count=len(chunks),
        embedding_dim=len(embeddings[0]) if embeddings else 0,
        model=EMBEDDING_MODEL
    )
    
    return len(chunks), result['tokens'], result['cost']


# 헤더
st.title("💬 FlowNote MVP")

# 사이드바: 파일 통계
with st.sidebar:
    st.header("📊 파일 통계")
    
    stats = st.session_state.metadata.get_statistics()
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("총 파일", f"{stats['total_files']}개")
        st.metric("총 청크", f"{stats['total_chunks']}개")
    
    with col2:
        st.metric("총 용량", f"{stats['total_size_mb']:.2f} MB")
        st.metric("모델 수", f"{len(stats['models_used'])}개")
    
    st.divider()
    
    st.header("📂 파일 목록")
    
    all_files = st.session_state.metadata.get_all_files()
    
    if all_files:
        # ✅ 딕셔너리를 리스트로 변환하고 생성 시간 기준 정렬
        file_items = sorted(
            all_files.items(),
            key=lambda x: x[1].get('created_at', ''),
            reverse=True  # 최신 순
        )
        
        # ✅ 전체 파일 표시 (최대 10개로 제한)
        display_count = min(len(file_items), 10)
        st.caption(f"최근 {display_count}개 파일")
        
        for file_id, file_data in file_items[:display_count]:
            with st.expander(f"📄 {file_data.get('file_name', 'Unknown')}"):
                st.text(f"크기: {file_data.get('file_size_mb', 0):.2f} MB")
                st.text(f"청크: {file_data.get('chunk_count', 0)}개")
                st.text(f"모델: {file_data.get('embedding_model', 'N/A')}")
                st.text(f"업로드: {file_data.get('created_at', 'N/A')}")
    else:
        st.info("업로드된 파일이 없습니다.")

# 메인 영역: 탭
tab1, tab2, tab3 = st.tabs(["📤 파일 업로드", "🔍 검색", "📊 히스토리"])

# 탭 1: 파일 업로드
with tab1:
    st.header("📤 파일 업로드")
    st.caption("텍스트 파일을 업로드하여 자동으로 처리합니다.")
    
    st.subheader("파일 선택")
    uploaded_file = st.file_uploader(
        "Drag and drop file here",
        type=['txt', 'md'],
        label_visibility="collapsed"
    )
    
    if uploaded_file:
        st.write(f"📄 **{uploaded_file.name}** ({uploaded_file.size / 1024:.1f} KB)")
        
        if st.button("📤 처리 시작", type="primary"):
            with st.spinner("파일 처리 중..."):
                try:
                    # 파일 ID 생성
                    file_id = f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
                    
                    # 파일 저장
                    file_path = save_file(uploaded_file)
                    
                    # 파일 처리 (청킹 → 임베딩 → FAISS)
                    uploaded_file.seek(0)  # 파일 포인터 리셋
                    chunks, tokens, cost = process_uploaded_file(uploaded_file, file_id)
                    
                    st.success("✅ 파일 처리 완료!")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("청크 수", f"{chunks}개")
                    with col2:
                        st.metric("토큰 수", f"{tokens}개")
                    with col3:
                        st.metric("예상 비용", f"${cost:.6f}")
                    
                    st.info("💡 이제 검색 탭에서 파일 내용을 검색할 수 있습니다!")
                    
                except Exception as e:
                    st.error(f"❌ 처리 실패: {str(e)}")

# 탭 2: 검색
with tab2:
    st.header("🔍 검색")
    st.caption("업로드한 파일에서 내용을 검색합니다.")
    
    query = st.text_input("검색어를 입력하세요", placeholder="예: FlowNote 사용법")
    k = st.slider("결과 개수", 1, 10, 3)
    
    if st.button("🔍 검색", type="primary"):
        if query:
            with st.spinner("검색 중..."):
                # FAISS 검색
                results = st.session_state.retriever.search(query, k=k)
                
                # 검색 기록 저장
                search_id = st.session_state.search_history.add_search(
                    query=query,
                    results_count=len(results),
                    top_results=[r['text'][:100] for r in results[:3]] if results else []
                )
                
                # 결과 표시
                if results:
                    st.success(f"✅ {len(results)}개 결과 발견")
                    
                    for i, result in enumerate(results, 1):
                        with st.container():
                            st.subheader(f"{i}위 (유사도: {result['similarity']:.4f})")
                            st.write(result['text'])
                            st.divider()
                else:
                    st.warning("⚠️ 검색 결과가 없습니다.")
        else:
            st.warning("⚠️ 검색어를 입력해주세요.")

# 탭 3: 히스토리
with tab3:
    st.header("📊 검색 히스토리")
    
    # ✅ get_recent_searches()는 리스트를 반환!
    recent_searches = st.session_state.search_history.get_recent_searches(limit=10)
    
    if recent_searches:
        # ✅ 이미 리스트이므로 바로 순회!
        for search_data in recent_searches:
            with st.expander(f"🔍 {search_data['query']} (결과: {search_data['results_count']}개)"):
                st.text(f"시간: {search_data['created_at']}")
                
                if search_data.get('top_results'):
                    st.subheader("상위 결과:")
                    for i, result in enumerate(search_data['top_results'], 1):
                        st.write(f"{i}. {result}...")
                else:
                    st.info("0개 결과 발견")
    else:
        st.info("아직 검색 기록이 없습니다.")

# 푸터
st.divider()
st.caption("FlowNote MVP v1.0 | Made with ❤️ by Jay")
