# ━━━━━━━━━━━━━━━━━━━━
# app.py
# ━━━━━━━━━━━━━━━━━━━━

import streamlit as st
import numpy as np
from pathlib import Path
from datetime import datetime

from backend.embedding import EmbeddingGenerator
from backend.chunking import TextChunker
from backend.faiss_search import FAISSRetriever
from backend.metadata import FileMetadata
from backend.search_history import SearchHistory
from backend.classifier.para_classifier import PARAClassifier
from backend.validators import FileValidator
from backend.exceptions import FileValidationError
from backend.utils import format_file_size, load_pdf
from backend.export import MarkdownExporter
from backend.routes.conflict_routes import router as conflict_router    # 추가

# 추가
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 추가
app = FastAPI()

# Router 등록
app.include_router(conflict_router, prefix="/api/conflict", tags=["conflict"])

st.set_page_config(page_title="FlowNote", page_icon="📚", layout="wide")

# 세션 상태 초기화
if "faiss_retriever" not in st.session_state:
    st.session_state.faiss_retriever = None
if "file_metadata" not in st.session_state:
    st.session_state.file_metadata = FileMetadata()
if "search_history" not in st.session_state:
    st.session_state.search_history = SearchHistory()
if "classifier" not in st.session_state:
    st.session_state.classifier = PARAClassifier()
if "classification_result" not in st.session_state:
    st.session_state.classification_result = None
if "current_file" not in st.session_state:
    st.session_state.current_file = None
if "current_file_content" not in st.session_state:
    st.session_state.current_file_content = None
if "uploaded_file_key" not in st.session_state:
    st.session_state.uploaded_file_key = 0
if "show_folder_select" not in st.session_state:
    st.session_state.show_folder_select = False
if "last_search_results" not in st.session_state:
    st.session_state.last_search_results = None
if "last_search_query" not in st.session_state:
    st.session_state.last_search_query = None

def save_to_para_folder(filename, content, category):
    base_path = Path("data/exports")
    category_path = base_path / category
    category_path.mkdir(parents=True, exist_ok=True)
    file_path = category_path / filename
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return str(file_path)

st.title("📚 FlowNote")
st.markdown("**AI 기반 문서 검색 & PARA 분류 시스템**")

# 사이드바
with st.sidebar:
    st.header("📊 시스템 정보")
    
    # 파일 메타데이터
    if st.session_state.file_metadata.metadata:
        st.subheader("업로드된 파일")
        stats = st.session_state.file_metadata.get_statistics()
        st.metric("전체 파일", stats['total_files'])
        st.metric("전체 청크", stats['total_chunks'])
        
        with st.expander("📄 파일 상세"):
            for file_id, file_info in st.session_state.file_metadata.metadata.items():
                st.markdown(f"**{file_info['file_name']}**")
                st.text(f"크기: {file_info['file_size_mb']} MB")
                st.text(f"청크: {file_info['chunk_count']}개")
                st.divider()
    
    # 검색 히스토리
    st.divider()
    st.subheader("🔍 검색 히스토리")
    history = st.session_state.search_history.get_recent_searches(5)
    
    if history:
        for item in history:
            st.text(f"🔎 {item['query']}")
            st.caption(f"{item['created_at']} | {item['results_count']}개 결과")
        
        if st.button("🗑️ 히스토리 삭제", use_container_width=True):
            st.session_state.search_history.clear_history()
            st.rerun()
    else:
        st.info("검색 기록이 없습니다")

tab1, tab2 = st.tabs(["🔍 문서 검색", "🤖 PARA 분류"])

# TAB 1: 문서 검색
with tab1:
    st.header("🔍 문서 검색")
    
    uploaded_files = st.file_uploader(
        "문서 업로드 (PDF, TXT, MD)",
        type=['pdf', 'txt', 'md'],
        accept_multiple_files=True
    )
    
    if uploaded_files and st.button("📄 파일 처리"):
        doc_list = []
        
        with st.status("파일 처리 중...", expanded=True) as status:
            for uploaded_file in uploaded_files:
                try:
                    if uploaded_file.type == "application/pdf":
                        content = load_pdf(uploaded_file)
                    else:
                        content = uploaded_file.read().decode('utf-8')
                    
                    doc_list.append({
                        'name': uploaded_file.name,
                        'content': content,
                        'size': uploaded_file.size,
                        'type': uploaded_file.type
                    })
                    
                except Exception as e:
                    st.error(f"❌ {uploaded_file.name} 처리 실패: {str(e)}")
                    continue
            
            if doc_list:
                st.write("📊 텍스트 분석 중...")
                chunker = TextChunker()
                all_chunks = []
                chunk_metadata = []
                
                for doc in doc_list:
                    chunks = chunker.chunk_text(doc['content'])
                    all_chunks.extend(chunks)
                    for chunk in chunks:
                        chunk_metadata.append({
                            'filename': doc['name'],
                            'file_type': doc['type']
                        })
                
                st.write("🔮 임베딩 생성 중...")
                embedder = EmbeddingGenerator()
                result = embedder.generate_embeddings(all_chunks)
                
                embeddings_list = result['embeddings']
                embeddings_array = np.array(embeddings_list)
                
                st.write("🔍 검색 인덱스 구축 중...")
                
                documents = []
                for chunk, meta in zip(all_chunks, chunk_metadata):
                    documents.append({
                        "content": chunk,
                        "metadata": meta
                    })
                
                retriever = FAISSRetriever(dimension=embeddings_array.shape[1])
                retriever.add_documents(embeddings_array, documents)
                
                st.session_state.faiss_retriever = retriever
                
                for doc in doc_list:
                    count = sum(1 for m in chunk_metadata if m['filename'] == doc['name'])
                    st.session_state.file_metadata.add_file(
                        file_name=doc['name'],
                        file_size=doc['size'],
                        chunk_count=count,
                        embedding_dim=embeddings_array.shape[1]
                    )
                
                status.update(label="✅ 처리 완료!", state="complete", expanded=False)
                st.success(f"✅ {len(doc_list)}개 파일, {len(all_chunks)}개 청크 처리 완료!")
    
    if st.session_state.faiss_retriever:
        st.divider()
        query = st.text_input("🔍 검색어를 입력하세요")
        k = st.slider("검색 결과 개수", 1, 10, 3)
        
        if query and st.button("검색"):
            results = st.session_state.faiss_retriever.search(query, k=k)
            st.session_state.search_history.add_search(query=query, results_count=len(results))
            st.session_state.last_search_results = results
            st.session_state.last_search_query = query
            
            st.subheader(f"📊 검색 결과 ({len(results)}개)")
            for i, result in enumerate(results, 1):
                with st.expander(f"결과 #{i} | {result['metadata']['filename']} | 점수: {result['score']:.4f}"):
                    st.markdown(result['content'])
        
        # MD 내보내기 버튼
        if st.session_state.last_search_results:
            st.divider()
            if st.button("📥 검색 결과 MD로 내보내기", use_container_width=True):
                exporter = MarkdownExporter()
                md_content = exporter.export_search_results(
                    query=st.session_state.last_search_query,
                    results=st.session_state.last_search_results
                )
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"flownote_search_{timestamp}.md"
                
                st.download_button(
                    label="💾 다운로드",
                    data=md_content,
                    file_name=filename,
                    mime="text/markdown",
                    use_container_width=True
                )
    else:
        st.info("📤 먼저 문서를 업로드하고 처리해주세요")

# TAB 2: PARA 분류
with tab2:
    st.header("🤖 PARA 분류")
    
    uploaded_file_para = st.file_uploader(
        "분류할 파일 업로드 (PDF, TXT, MD)",
        type=['pdf', 'txt', 'md'],
        key=f"para_uploader_{st.session_state.uploaded_file_key}"
    )
    
    if uploaded_file_para:
        st.info(f"📄 업로드된 파일: **{uploaded_file_para.name}**")
        
        if st.button("🔍 분류 시작"):
            with st.spinner("AI가 문서를 분석하고 있습니다..."):
                try:
                    if uploaded_file_para.type == "application/pdf":
                        text = load_pdf(uploaded_file_para)
                    else:
                        text = uploaded_file_para.read().decode('utf-8')
                    
                    st.session_state.current_file = uploaded_file_para
                    st.session_state.current_file_content = text
                    
                    result = st.session_state.classifier.classify(
                        filename=uploaded_file_para.name,
                        content=text
                    )
                    st.session_state.classification_result = result
                    st.success("✅ 분류 완료!")
                    
                except Exception as e:
                    st.error(f"❌ 분류 실패: {str(e)}")
    
    if st.session_state.classification_result:
        result = st.session_state.classification_result
        
        st.divider()
        st.subheader("📊 분류 결과")
        
        category_emoji = {"P": "🚀", "A": "🎯", "R": "📚", "AR": "📦"}
        category_names = {"P": "Projects", "A": "Areas", "R": "Resources", "AR": "Archives"}
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.metric("분류 카테고리", f"{category_emoji[result['category']]} {category_names[result['category']]}")
        with col2:
            st.metric("신뢰도", f"{result['confidence']:.1%}")
        
        st.markdown("### 💡 분류 근거")
        st.info(result['reason'])
        
        st.markdown("### 📂 제안 폴더")
        st.success(f"`data/exports/{result['category']}/`")
        
        st.divider()
        
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            if st.button("💾 제안 폴더에 저장하기", use_container_width=True):
                saved_path = save_to_para_folder(
                    st.session_state.current_file.name,
                    st.session_state.current_file_content,
                    result['category']
                )
                st.success(f"✅ 저장 완료: `{saved_path}`")
        
        with col_btn2:
            if st.button("📂 다른 폴더에 저장하기", use_container_width=True):
                st.session_state.show_folder_select = True
        
        if st.session_state.show_folder_select:
            selected_category = st.selectbox(
                "카테고리 선택",
                options=["P", "A", "R", "AR"],
                format_func=lambda x: f"{category_emoji[x]} {category_names[x]}"
            )
            
            if st.button("💾 선택한 폴더에 저장"):
                saved_path = save_to_para_folder(
                    st.session_state.current_file.name,
                    st.session_state.current_file_content,
                    selected_category
                )
                st.success(f"✅ 저장 완료: `{saved_path}`")
                st.session_state.show_folder_select = False
        
        st.divider()
        if st.button("새로운 파일 분류하기", use_container_width=True, type="primary"):
            st.session_state.classification_result = None
            st.session_state.current_file = None
            st.session_state.current_file_content = None
            st.session_state.show_folder_select = False
            st.session_state.uploaded_file_key += 1
            st.rerun()

st.divider()
st.caption("FlowNote MVP v3.3_compiled | Made with ❤️ by Jay")