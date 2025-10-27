# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# app.py (파일 업로드 에러 핸들링 추가)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
FlowNote MVP - Streamlit UI
"""

import streamlit as st
import os
from datetime import datetime
import numpy as np

# backend 클래스 임포트
from backend.embedding import EmbeddingGenerator
from backend.chunking import TextChunker
from backend.faiss_search import FAISSRetriever
from backend.metadata import FileMetadata
from backend.search_history import SearchHistory

# 페이지 설정
st.set_page_config(
    page_title="FlowNote",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 세션 상태 초기화
if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = []
if "documents" not in st.session_state:
    st.session_state.documents = []
if "faiss_retriever" not in st.session_state:
    st.session_state.faiss_retriever = None
if "file_metadata_manager" not in st.session_state:
    st.session_state.file_metadata_manager = FileMetadata()
if "search_history_manager" not in st.session_state:
    st.session_state.search_history_manager = SearchHistory()

# 청커 초기화
chunker = TextChunker(chunk_size=500, chunk_overlap=50)

# 임베딩 생성기 초기화
embedding_generator = EmbeddingGenerator()


# Document 클래스 정의
class SimpleDocument:
    """간단한 문서 클래스"""
    def __init__(self, page_content: str, metadata: dict = None):
        self.page_content = page_content
        self.metadata = metadata or {}


# 메인 UI
st.title("📚 FlowNote")
st.markdown("### AI 기반 문서 검색 및 질의응답 시스템")

# 사이드바
with st.sidebar:
    st.header("⚙️ 설정")
    
    # 파일 업로드
    uploaded_files = st.file_uploader(
        "📁 문서 업로드 (PDF/TXT)",
        type=["pdf", "txt"],
        accept_multiple_files=True,
        help="PDF 또는 TXT 파일을 업로드하세요."
    )
    
    if uploaded_files:
        if st.button("📤 파일 처리하기", type="primary"):
            with st.spinner("파일을 처리하는 중입니다..."):
                try:
                    # 파일 저장
                    os.makedirs("uploaded_files", exist_ok=True)
                    saved_files = []
                    
                    for uploaded_file in uploaded_files:
                        file_path = os.path.join("uploaded_files", uploaded_file.name)
                        with open(file_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())
                        saved_files.append(file_path)
                    
                    # 문서 로드 및 청크 분할
                    all_texts = []
                    all_documents = []
                    
                    for file_path in saved_files:
                        # 파일 읽기
                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                text = f.read()
                        except UnicodeDecodeError:
                            with open(file_path, "r", encoding="cp949") as f:
                                text = f.read()
                        
                        # 청크 분할
                        chunks_with_meta = chunker.chunk_with_metadata(
                            text, 
                            metadata={"source": os.path.basename(file_path)}
                        )
                        
                        for chunk in chunks_with_meta:
                            all_texts.append(chunk["text"])
                            all_documents.append(SimpleDocument(
                                page_content=chunk["text"],
                                metadata=chunk["metadata"]
                            ))
                        
                        # 파일 메타데이터 저장
                        file_size = os.path.getsize(file_path)
                        st.session_state.file_metadata_manager.add_file(
                            file_name=os.path.basename(file_path),
                            file_size=file_size,
                            chunk_count=len(chunks_with_meta),
                            embedding_dim=1536,
                            model="text-embedding-3-small"
                        )
                    
                    if all_texts:
                        # 임베딩 생성
                        embed_result = embedding_generator.generate_embeddings(all_texts)
                        embeddings = embed_result['embeddings']
                        
                        # FAISS Retriever 생성
                        retriever = FAISSRetriever(dimension=1536)
                        retriever.add_documents(all_texts, embeddings)
                        
                        # 세션 상태 저장
                        st.session_state.documents = all_documents
                        st.session_state.uploaded_files = saved_files
                        st.session_state.faiss_retriever = retriever
                        
                        st.success(f"✅ {len(uploaded_files)}개 파일이 성공적으로 처리되었습니다!")
                        st.info(f"📊 총 {len(all_documents)}개의 청크가 생성되었습니다.")
                    else:
                        st.error("❌ 파일 처리에 실패했습니다.")
                        
                except Exception as e:
                    st.error(f"❌ 오류가 발생했습니다: {str(e)}")
    
    st.divider()
    
    # 업로드된 파일 목록
    if st.session_state.uploaded_files:
        st.subheader("📂 업로드된 파일")
        all_files = st.session_state.file_metadata_manager.get_all_files()
        
        for file_id, file_info in all_files.items():
            with st.expander(f"📄 {file_info['file_name']}"):
                st.write(f"**크기:** {file_info['file_size_mb']} MB")
                st.write(f"**청크 수:** {file_info['chunk_count']}")
                st.write(f"**모델:** {file_info['embedding_model']}")
                st.write(f"**업로드:** {file_info['created_at']}")

# 메인 컨텐츠
if st.session_state.faiss_retriever is not None:
    # 검색 섹션
    st.subheader("🔍 문서 검색")
    
    col1, col2 = st.columns([4, 1])
    with col1:
        query = st.text_input(
            "검색어를 입력하세요",
            placeholder="예: 프로젝트 목표가 무엇인가요?",
            help="문서에서 찾고 싶은 내용을 입력하세요."
        )
    with col2:
        k = st.number_input("결과 수", min_value=1, max_value=10, value=3)
    
    if st.button("🔍 검색", type="primary"):
        if query:
            with st.spinner("검색 중입니다..."):
                try:
                    # FAISS 검색
                    search_results = st.session_state.faiss_retriever.search(query, k=k)
                    
                    if search_results:
                        # 문서와 유사도 매칭
                        results = []
                        result_texts = []
                        
                        for result in search_results:
                            # 텍스트로 문서 찾기
                            for doc in st.session_state.documents:
                                if doc.page_content == result['text']:
                                    results.append((doc, result['similarity']))
                                    result_texts.append(doc.page_content[:100])
                                    break
                        
                        # 검색 히스토리에 추가
                        st.session_state.search_history_manager.add_search(
                            query=query,
                            results_count=len(results),
                            top_results=result_texts
                        )
                        
                        st.success(f"✅ {len(results)}개의 결과를 찾았습니다!")
                        
                        # 검색 결과 표시
                        for i, (doc, score) in enumerate(results, 1):
                            with st.expander(f"📄 결과 {i} (유사도: {score:.2%})"):
                                st.markdown(f"**내용:**\n{doc.page_content}")
                                st.markdown(f"**출처:** {doc.metadata.get('source', 'Unknown')}")
                    else:
                        st.warning("검색 결과가 없습니다.")
                        
                except Exception as e:
                    st.error(f"❌ 검색 중 오류가 발생했습니다: {str(e)}")
        else:
            st.warning("⚠️ 검색어를 입력해주세요.")
    
    # 검색 히스토리
    st.divider()
    st.subheader("📊 검색 히스토리")
    
    recent_searches = st.session_state.search_history_manager.get_recent_searches(limit=10)
    
    if recent_searches:
        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("🗑️ 히스토리 삭제"):
                st.session_state.search_history_manager.clear_all()
                st.rerun()
        
        for search in recent_searches:
            with st.expander(f"🕐 {search['created_at']} - {search['query']}"):
                st.markdown(f"**검색어:** {search['query']}")
                st.markdown(f"**결과 수:** {search['results_count']}")
                
                if search['top_results']:
                    st.markdown("**상위 결과:**")
                    for result in search['top_results']:
                        st.markdown(f"- {result}")
    else:
        st.info("검색 히스토리가 없습니다.")

else:
    # 초기 화면
    st.info(
        """
        👋 **FlowNote에 오신 것을 환영합니다!**
        
        시작하려면:
        1. 왼쪽 사이드바에서 PDF 또는 TXT 파일을 업로드하세요
        2. "파일 처리하기" 버튼을 클릭하세요
        3. 검색어를 입력하여 문서를 검색하세요
        
        💡 **팁:** 여러 파일을 한 번에 업로드할 수 있습니다!
        """
    )



# ━━━━━━━━━━━━━━━━━━━━━━
# 푸터
# ━━━━━━━━━━━━━━━━━━━━━━
st.divider()
st.caption("FlowNote MVP v1.1 | Made with ❤️ by Jay")
