# streamlit/test_ui5.py

"""
FlowNote 통합 UI - 온보딩 플로우 추가
- main
    - tab1 : 온보딩
    - tab2 : 파일 업로드 & 분류
    - tab3 : 키워드 검색
    - tab4 : 파일 통계 (← tab2의 정보 실시간 반영되도록 수정)
    - tab5 : 메타데이터 + 사용자 정보 기반 필터링 추가
- 사이드바
    - 온보딩 상태 추가
    - 분류 히스토리
"""

import requests 
import os
import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent 
sys.path.insert(0, str(project_root))

# Streamlit + 환경변수 로드
import streamlit as st
from dotenv import load_dotenv

# 로컬에서는 .env 로드
load_dotenv()

# 배포 환경에서는 Streamlit Secrets 로드
try:
    if hasattr(st, 'secrets') and len(st.secrets) > 0:
        for key in ["EMBEDDING_API_KEY", "EMBEDDING_BASE_URL", "EMBEDDING_MODEL",
                    "EMBEDDING_LARGE_API_KEY", "EMBEDDING_LARGE_BASE_URL", "EMBEDDING_LARGE_MODEL",
                    "GPT4O_API_KEY", "GPT4O_BASE_URL", "GPT4O_MODEL",
                    "GPT4O_MINI_API_KEY", "GPT4O_MINI_BASE_URL", "GPT4O_MINI_MODEL",
                    "GPT41_API_KEY", "GPT41_BASE_URL", "GPT41_MODEL"]:
            if key in st.secrets:
                os.environ[key] = st.secrets[key]
except:
    pass

from datetime import datetime
import json
import pandas as pd
import numpy as np

# Backend 임포트
from backend.embedding import EmbeddingGenerator
from backend.chunking import TextChunker
from backend.faiss_search import FAISSRetriever
from backend.metadata import FileMetadata
from backend.search_history import SearchHistory
from backend.classifier.para_classifier import PARAClassifier
from backend.validators import FileValidator
from backend.exceptions import FileValidationError
from backend.classifier.para_agent_wrapper import run_para_agent_sync
from backend.database.metadata_schema import ClassificationMetadataExtender
from backend.database.connection import DatabaseConnection
from backend.utils import format_file_size, load_pdf
from backend.export import MarkdownExporter
from backend.modules import extract_text_from_pdf

# 페이지 설정
st.set_page_config(
    page_title="FlowNote 통합 UI 테스트",
    page_icon="📚",
    layout="wide"
)

# 세션 상태 초기화
if "classification_history" not in st.session_state:
    st.session_state.classification_history = []

if "db_extender" not in st.session_state:
    st.session_state.db_extender = ClassificationMetadataExtender()

# 온보딩 플로우용 세션 상태
if "onboarding_step" not in st.session_state:
    st.session_state.onboarding_step = 1

if "onboarding_user_id" not in st.session_state:
    st.session_state.onboarding_user_id = None

if "onboarding_name" not in st.session_state:
    st.session_state.onboarding_name = ""

if "onboarding_occupation" not in st.session_state:
    st.session_state.onboarding_occupation = ""

if "suggested_areas" not in st.session_state:
    st.session_state.suggested_areas = []

if "selected_areas" not in st.session_state:
    st.session_state.selected_areas = []


# 파일 저장 정의 함수
def save_to_para_folder(filename, content, category):
    base_path = Path("data/exports")
    category_path = base_path / category
    category_path.mkdir(parents=True, exist_ok=True)
    file_path = category_path / filename
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return str(file_path)


# ==========================
# 타이틀
# ==========================

st.title("📚 FlowNote 통합 테스트 UI")
st.markdown("**온보딩 → 분류 → 키워드 검색 → 통계 → 메타데이터**")


# ==========================
# 사이드바: 분류 히스토리 등
# ==========================
with st.sidebar:
    st.header("👤 사용자 정보")
    
    if st.session_state.onboarding_step == 3:
        st.success("✅ 온보딩 완료")
        st.write(f"이름: {st.session_state.onboarding_name}")
        st.write(f"직업: {st.session_state.onboarding_occupation}")
        st.write(f"User ID: {st.session_state.onboarding_user_id[:12]}...")
    else:
        st.warning("⚠️ 온보딩 필요")
        st.info("Tab1에서 온보딩을 완료하세요")

    st.divider()

    # 분류 히스토리
    st.header("📊 분류 히스토리")
    if st.session_state.classification_history:
        st.metric("총 분류 파일", len(st.session_state.classification_history))
        with st.expander("최근 분류 결과", expanded=True):
            for idx, item in enumerate(reversed(st.session_state.classification_history[-5:]), 1):
                st.markdown(f"**{idx}. {item['filename']}**")
                st.caption(f"카테고리: {item['category']} ({item['confidence']:.0%})")
                st.caption(f"시간: {item['timestamp']}")
        if st.button("초기화", key="clear_history"):
            st.session_state.classification_history = []
            st.rerun()
    else:
        st.info("아직 분류된 파일이 없습니다")


# ==========================
# main (tab1, 2, 3, 4, 5)
# ==========================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🚀 온보딩",
    "📤 파일 분류",
    "🔍 키워드 검색",
    "🎯 분류 통계",
    "📊 메타데이터"
])


# ────────────────
# TAB 1: 온보딩
# ────────────────
with tab1:
    st.header("🚀 온보딩 플로우")
    if st.session_state.onboarding_step == 1:
        # Step 1
        with st.form("step1_form"):
            name = st.text_input("이름", value=st.session_state.onboarding_name, placeholder="예: 홍길동")
            occupation = st.text_input("직업", value=st.session_state.onboarding_occupation, placeholder="예: 개발자, 디자이너")
            submitted = st.form_submit_button("다음 단계 →")
            if submitted:
                if not name or not occupation:
                    st.error("⚠️ 이름/직업을 입력해주세요")
                else:
                    # API 요청
                    response1 = requests.post(
                        "http://127.0.0.1:8000/api/onboarding/step1",
                        json={"occupation": occupation, "name": name})
                    if response1.status_code == 200:
                        result1 = response1.json()
                        user_id = result1['user_id']
                        response2 = requests.get(
                            f"http://127.0.0.1:8000/api/onboarding/suggest-areas?user_id={user_id}&occupation={occupation}")
                        if response2.status_code == 200:
                            result2 = response2.json()
                            st.session_state.onboarding_user_id = user_id
                            st.session_state.onboarding_name = name
                            st.session_state.onboarding_occupation = occupation
                            # 영역 처리
                            if 'suggested_areas' in result2:
                                st.session_state.suggested_areas = result2['suggested_areas']
                            elif 'areas' in result2:
                                st.session_state.suggested_areas = result2['areas']
                            st.session_state.onboarding_step = 2
                            st.rerun()
                        else:
                            st.error(f"영역 추천 실패: {response2.status_code}")
                    else:
                        st.error(f"Step1 실패: {response1.status_code}")
    elif st.session_state.onboarding_step == 2:
        # Step 2
        st.subheader("Step 2: 관심 영역 선택")
        for area in st.session_state.suggested_areas:
            checked = st.checkbox(area, key=f"area_{area}")
            if checked and area not in st.session_state.selected_areas:
                st.session_state.selected_areas.append(area)
            elif not checked and area in st.session_state.selected_areas:
                st.session_state.selected_areas.remove(area)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("← 이전", key="onboarding_prev"):
                st.session_state.onboarding_step = 1
                st.rerun()
        with col2:
            if st.button("저장하고 시작 →", key="onboarding_next", disabled=(len(st.session_state.selected_areas) == 0)):
                response = requests.post(
                    "http://127.0.0.1:8000/api/onboarding/save-context",
                    json={"user_id": st.session_state.onboarding_user_id, "selected_areas": st.session_state.selected_areas}
                )
                if response.status_code == 200:
                    st.session_state.onboarding_step = 3
                    st.rerun()
                else:
                    st.error(f"저장 실패: {response.status_code}")
    elif st.session_state.onboarding_step == 3:
        st.subheader("🎉 온보딩 완료!")
        st.success(f"{st.session_state.onboarding_name}님의 설정이 완료되었습니다.")
        st.write(f"직업: {st.session_state.onboarding_occupation}")
        st.write(f"사용자 ID: {st.session_state.onboarding_user_id}")
        st.write("선택 영역:")
        for area in st.session_state.selected_areas:
            st.write(f"- {area}")
        if st.button("온보딩 다시하기"):
            st.session_state.onboarding_step = 1
            st.session_state.onboarding_user_id = None
            st.session_state.onboarding_name = ""
            st.session_state.onboarding_occupation = ""
            st.session_state.suggested_areas = []
            st.session_state.selected_areas = []
            st.rerun()


# ────────────────
# TAB 2: 파일 분류
# ────────────────

with tab2:
    st.header("📤 파일 업로드 & 자동 분류")
    
    # ✅ 온보딩 완료 여부 확인
    onboarding_complete = (
        st.session_state.onboarding_step == 3 and 
        st.session_state.onboarding_user_id is not None
    )
    
    if not onboarding_complete:
        st.warning("⚠️ 먼저 온보딩을 완료해주세요! (Tab1)")
        st.info("온보딩을 완료하면 당신의 맥락에 맞는 정확한 분류를 제공합니다.")
        st.stop()
    
    # ✅ 온보딩 정보 표시
    with st.expander("👤 현재 사용자 정보", expanded=False):
        st.write(f"**이름:** {st.session_state.onboarding_name}")
        st.write(f"**직업:** {st.session_state.onboarding_occupation}")
        st.write(f"**User ID:** {st.session_state.onboarding_user_id}")
        st.write(f"**관심 영역:**")
        for area in st.session_state.selected_areas:
            st.write(f"  - {area}")
    
    uploaded_file = st.file_uploader(
        "분류할 파일 업로드", type=['pdf', 'txt', 'md'], key="file_uploader_tab2"
    )
    
    if uploaded_file:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("파일명", uploaded_file.name)
        with col2:
            st.metric("파일 크기", f"{uploaded_file.size / 1024:.2f} KB")
        with col3:
            st.metric("파일 타입", uploaded_file.type.split('/')[-1].upper())
        
        # 분류 버튼
        if st.button("🚀 분류 시작", key="classify_btn_tab2"):
            with st.spinner("AI 분석 중... (사용자 맥락 반영)"):
                try:
                    # 1. 텍스트 추출
                    if uploaded_file.type == "application/pdf":
                        text = load_pdf(uploaded_file)
                    else:
                        text = uploaded_file.read().decode('utf-8')
                    
                    # 2. 메타데이터 구성 (✨ user_id 추가!)
                    metadata = {
                        "filename": uploaded_file.name,
                        "file_size": uploaded_file.size,
                        "file_type": uploaded_file.type,
                        "uploaded_at": datetime.now().isoformat(),
                        # 사용자 정보 추가
                        "user_id": st.session_state.onboarding_user_id,
                        "user_name": st.session_state.onboarding_name,
                        "user_occupation": st.session_state.onboarding_occupation,
                        "user_areas": st.session_state.selected_areas
                    }
                    
                    # 3. 분류 실행 (✨ user_context 추가!)
                    from backend.classifier.context_injector import get_context_injector
                    
                    injector = get_context_injector()
                    
                    # 3-1. 기본 분류
                    classification_result = run_para_agent_sync(
                        text=text[:2000],
                        metadata=metadata
                    )
                    
                    # 3-2. 사용자 맥락 주입
                    classification_result = injector.inject_context_from_user_id(
                        user_id=st.session_state.onboarding_user_id,
                        ai_result=classification_result
                    )
                    
                    # 4. DB 저장
                    file_id = st.session_state.db_extender.save_classification_result(
                        result=classification_result,
                        filename=uploaded_file.name
                    )
                    
                    # 5. 히스토리 저장
                    history_item = {
                        "filename": uploaded_file.name,
                        "category": classification_result.get('category', 'Unknown'),
                        "confidence": classification_result.get('confidence', 0),
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "file_id": file_id,
                        "user_id": st.session_state.onboarding_user_id,
                        "context_injected": classification_result.get('context_injected', False)
                    }
                    st.session_state.classification_history.append(history_item)
                    
                    # 6. 결과 표시
                    st.success("✅ 분류 완료!")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("카테고리", classification_result.get('category', 'N/A'))
                        st.metric("신뢰도", f"{classification_result.get('confidence', 0):.0%}")
                    
                    with col2:
                        st.metric("맥락 반영", 
                                "✅ 반영됨" if classification_result.get('context_injected') else "❌ 미반영")
                        keyword_tags = classification_result.get('keyword_tags', [])
                        st.metric("키워드 수", len(keyword_tags))
                    
                    # 7. 상세 정보
                    with st.expander("📊 상세 분류 정보", expanded=True):
                        st.json(classification_result)
                    
                except Exception as e:
                    st.error(f"❌ 분류 실패: {str(e)}")
                    st.exception(e)

# ────────────────
# TAB 3: 키워드 검색
# ────────────────

with tab3:
    st.header("🔍 키워드 검색")
    
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
                            'file_type': doc['type'],
                            # 필요하다면 추가 메타데이터도 넣기
                        })
                
                st.write("🔮 임베딩 생성 중...")
                embedder = EmbeddingGenerator()
                result = embedder.generate_embeddings(all_chunks)
                
                embeddings_list = result['embeddings']
                embeddings_array = np.array(embeddings_list)
                
                st.write("🔍 검색 인덱스 구축 중...")
                                
                retriever = FAISSRetriever(dimension=embeddings_array.shape[1])
                retriever.add_documents(embeddings_array, [
                    {"content": chunk, "metadata": meta}
                    for chunk, meta in zip(all_chunks, chunk_metadata)
                ])
                
                st.session_state.faiss_retriever = retriever
                
                st.success(f"✅ {len(doc_list)}개 파일, {len(all_chunks)}개 청크 처리 완료!")
                
    retriever_exists = st.session_state.get('faiss_retriever') is not None
    if retriever_exists:
        st.divider()
        query = st.text_input("🔍 검색어를 입력하세요")
        k = st.slider("검색 결과 개수", 1, 10, 3)
        search_clicked = st.button("검색")
        if query and search_clicked:
            try:
                results = st.session_state['faiss_retriever'].search(query, k=k)
            except Exception as e:
                st.error(f"검색 중 오류 발생: {e}")
                results = []
            
            if 'search_history' not in st.session_state:
                st.session_state['search_history'] = []
            st.session_state['search_history'].append({
                "query": query,
                "results_count": len(results),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            st.session_state['last_search_results'] = results
            st.session_state['last_search_query'] = query
            
            st.subheader(f"📊 검색 결과 ({len(results)}개)")
            
            for i, result in enumerate(results, 1):
                meta = result.get('metadata', {})
                filename = meta.get('filename', 'unknown')
                filetype = meta.get('file_type', 'unknown')
                score = result.get('score', 0.0)
                keywords = meta.get('keyword_tags', [])
                confidence = meta.get('confidence_score', None)
                conf_text = f"{confidence:.0%}" if confidence is not None else "-"
                keywords_text = ", ".join(keywords[:5]) if keywords else "-"
                
                with st.expander(f"결과 #{i} | {filename} | {filetype} | 점수: {score:.4f}"):
                    st.markdown(result.get('content', ''))
                    st.markdown(f"**키워드:** {keywords_text}")
                    st.markdown(f"**신뢰도:** {conf_text}")
        
        last_results = st.session_state.get('last_search_results')
        last_query = st.session_state.get('last_search_query', '')
        if last_results:
            st.divider()
            export_clicked = st.button("📥 검색 결과 MD로 내보내기", width='stretch')
            if export_clicked:
                try:
                    exporter = MarkdownExporter()
                    md_content = exporter.export_search_results(query=last_query, results=last_results)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"flownote_search_{timestamp}.md"
                    st.download_button(
                        label="💾 다운로드",
                        data=md_content,
                        file_name=filename,
                        mime="text/markdown",
                        width='stretch'
                    )
                except Exception as e:
                    st.error(f"MD 내보내기 실패: {e}")
    else:
        st.info("📤 먼저 문서를 업로드하고 처리해주세요")


# ────────────────
# TAB 4: 분류 통계
# ────────────────

with tab4:
    st.header("🎯 분류 통계")
    if st.session_state.classification_history:
        from collections import Counter
        categories = [item['category'] for item in st.session_state.classification_history]
        category_counts = Counter(categories)
        st.metric("Projects", category_counts.get('Projects', 0))
        st.metric("Areas", category_counts.get('Areas', 0))
        st.metric("Resources", category_counts.get('Resources', 0))
        st.metric("Archives", category_counts.get('Archives', 0))
        confidences = [item['confidence'] for item in st.session_state.classification_history]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0
        st.metric("평균 신뢰도", f"{avg_confidence:.0%}")
        st.bar_chart(category_counts)
    else:
        st.info("분류 파일 없음")


# ────────────────
# TAB 5: 메타데이터
# ────────────────

with tab5:
    st.header("📊 메타데이터 확인")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("현재 세션 분류 결과")
    with col2:
        if st.button("🔄 새로고침", key="refresh_metadata"):
            st.rerun()
        # 사용자 ID 필터
        user_filter = st.selectbox(
            "🔍 사용자 필터",
            options=["전체"] + list(set([
                item.get('user_id', 'N/A')[:12] 
                for item in st.session_state.classification_history
            ])),
            key="user_filter"
        )
    
    # 1. 현재 세션 데이터 (st.session_state.classification_history)
    if st.session_state.classification_history:
        st.markdown("### 📝 이번 세션 분류 목록")
        
        # 필터링 로직 적용
        filtered_history = st.session_state.classification_history
        
        if user_filter != "전체":
            filtered_history = [
                item for item in st.session_state.classification_history
                if item.get('user_id', '').startswith(user_filter)
            ]
        
        session_data = []
        for item in st.session_state.classification_history:
            session_data.append({
                "파일명": item['filename'],
                "카테고리": item['category'],
                "신뢰도": f"{item['confidence']:.0%}",
                "시간": item['timestamp'],
                "맥락": "✅" if item.get('context_injected', False) else "❌",
                "User ID": item.get('user_id', 'N/A')[:12] + "..."
            })
        
        df_session = pd.DataFrame(session_data)
        st.dataframe(df_session, width='stretch')
        
        # 필터링된 통계
        st.divider()
        col1, col2, col3, col4, col5= st.columns(5)
        
        with col1:
            st.metric("필터 결과", len(filtered_history))
        
        with col2:
            st.metric("총 파일", len(st.session_state.classification_history))
        
        with col3:
            if filtered_history:
                avg_conf = sum(item['confidence'] for item in filtered_history) / len(filtered_history)
                st.metric("평균 신뢰도", f"{avg_conf:.0%}")
        
        with col4:
            context_count = sum(1 for item in filtered_history if item.get('context_injected', False))
            st.metric("맥락 반영", f"{context_count}/{len(filtered_history)}")
        
        with col5:
            if st.button("🗑️ 세션 초기화"):
                st.session_state.classification_history = []
                st.rerun()
    
    else:
        st.info("현재 세션에서 분류된 파일이 없습니다.")
    
    # 2. DB에 저장된 전체 데이터 (선택사항)
    st.divider()
    with st.expander("🗄️ 전체 DB 메타데이터 보기"):
        try:
            all_classifications = st.session_state.db_extender.get_all_classifications()
            
            if all_classifications:
                df_data = []
                for item in all_classifications:
                    df_data.append({
                        "파일명": item['filename'],
                        "카테고리": item['para_category'],
                        "신뢰도": f"{item['confidence_score']:.0%}",
                        "키워드": item['keyword_tags'][:50] if item['keyword_tags'] else "",
                        "충돌": "⚠️" if item['conflict_flag'] else "✅",
                        "Snapshot ID": item['snapshot_id'][:20] if item['snapshot_id'] else ""
                    })
                
                df_all = pd.DataFrame(df_data)
                st.dataframe(df_all, width='stretch')
                st.caption(f"총 {len(all_classifications)}개 항목")
            else:
                st.info("DB에 저장된 메타데이터가 없습니다")
        
        except Exception as e:
            st.error(f"DB 로드 실패: {e}")


# 하단 정보
st.divider()
st.caption("FlowNote MVP v3.4 | 사용자 맥락 통합 중 | Made with ❤️ by Jay")
