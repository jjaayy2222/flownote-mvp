# streamlit/test_ui6.py

"""
FlowNote 통합 UI - 온보딩 플로우 추가
- main
    - tab1 : 온보딩 → 선택 영역을 10개로 늘리고 사용자가 5개를 선택하도록 하기 
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
from backend.data_manager import DataManager

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
    st.title("📝 FlowNote-mvp-ver.3.5")
    st.markdown("---")

    st.header("👤 사용자 정보")
    
    if st.session_state.onboarding_step == 3:
        st.success("✅ 온보딩 완료")
        st.write(f"이름: {st.session_state.onboarding_name}")
        st.write(f"직업: {st.session_state.onboarding_occupation}")
        st.write(f"User ID: {st.session_state.onboarding_user_id[:12]}...")
        st.write("**선택한 Areas:**")
        for area in st.session_state.selected_areas:
            st.write(f"- {area}")
        
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

# ────────────────
# TAB 1: 온보딩 (완전 수정 버전)
# ────────────────
with tab1:
    st.header("🚀 온보딩: Areas 추천 및 선택")
    
    # onboarding_step 초기화
    if "onboarding_step" not in st.session_state:
        st.session_state.onboarding_step = 1
    
    
    # ============================================
    # Step 1: 기본 정보 입력
    # ============================================
    if st.session_state.onboarding_step == 1:
        st.subheader("Step 1: 기본 정보 입력")
        st.markdown("이름과 직업을 입력하면, GPT-4o가 당신의 직업에 맞는 **10개의 Areas**를 추천해 드립니다.")
        
        with st.form("step1_form"):
            name = st.text_input(
                "이름", 
                value=st.session_state.onboarding_name, 
                placeholder="예: Jay"
            )
            occupation = st.text_input(
                "직업", 
                value=st.session_state.onboarding_occupation, 
                placeholder="예: 개발자, 디자이너, 교사"
            )
            submitted = st.form_submit_button("다음 단계 →", use_container_width=True, type="primary")
            
            if submitted:
                if not name or not occupation:
                    st.error("⚠️ 이름과 직업을 모두 입력해주세요.")
                else:
                    with st.spinner("GPT-4o가 Areas를 추천 중입니다..."):
                        try:
                            # 1) 사용자 정보 저장 및 user_id 생성
                            response1 = requests.post(
                                "http://127.0.0.1:8000/api/onboarding/step1",
                                json={"occupation": occupation, "name": name},
                            )
                            
                            if response1.status_code == 200:
                                result1 = response1.json()
                                user_id = result1.get("user_id")
                                
                                if not user_id:
                                    st.error("❌ 유저 아이디를 받지 못했습니다.")
                                else:
                                    # 2) 영역 추천 API 호출
                                    response2 = requests.get(
                                        f"http://127.0.0.1:8000/api/onboarding/suggest-areas",
                                        params={"user_id": user_id, "occupation": occupation}
                                    )
                                    
                                    if response2.status_code == 200:
                                        result2 = response2.json()
                                        
                                        # 세션 상태 업데이트
                                        st.session_state.onboarding_name = name
                                        st.session_state.onboarding_occupation = occupation
                                        st.session_state.onboarding_user_id = user_id
                                        st.session_state.suggested_areas = result2.get("suggested_areas", [])
                                        
                                        # Step 2로 이동
                                        st.session_state.onboarding_step = 2
                                        st.rerun()
                                    else:
                                        st.error(f"❌ 영역 추천 API 실패: {response2.status_code}")
                            else:
                                st.error(f"❌ 사용자 정보 저장 API 실패: {response1.status_code}")
                                
                        except Exception as e:
                            st.error(f"❌ API 호출 실패: {e}")
                            st.exception(e)
    
    
    # ============================================
    # Step 2: 관심 영역 선택
    # ============================================
    elif st.session_state.onboarding_step == 2:
        st.subheader("Step 2: 관심 영역 선택")
        st.markdown(f"**{st.session_state.onboarding_name}님**, GPT-4o가 추천한 Areas 중 **정확히 5개**를 선택해주세요.")
        
        # 추천된 areas
        suggested = st.session_state.suggested_areas
        
        if len(suggested) < 5:
            st.warning(f"⚠️ 추천된 Areas가 5개 미만입니다 ({len(suggested)}개). GPT-4o 응답을 확인하세요.")
        
        # 영역 선택 (multiselect)
        selected = st.multiselect(
            f"추천된 Areas ({len(suggested)}개)",
            options=suggested,
            default=[],
            help="정확히 5개를 선택해주세요"
        )
        
        # 선택 개수 표시
        if len(selected) < 5:
            st.info(f"📊 현재 선택된 개수: {len(selected)}/5 (아직 {5 - len(selected)}개 더 필요)")
        elif len(selected) == 5:
            st.success(f"✅ 정확히 5개를 선택했습니다!")
        else:
            st.warning(f"⚠️ {len(selected)}개를 선택했습니다. 정확히 5개만 선택해주세요.")
        
        # 🔥 버튼 섹션
        st.divider()
        
        col1, col2 = st.columns([1, 3])
        
        with col1:
            if st.button("← 이전", use_container_width=True, key="step2_prev"):
                st.session_state.onboarding_step = 1
                st.rerun()
        
        with col2:
            # 5개 선택 여부에 따라 버튼 스타일 변경
            button_type = "primary" if len(selected) == 5 else "secondary"
            
            if st.button(
                "완료 →", 
                use_container_width=True, 
                type=button_type,
                key="step2_next"
            ):
                # 🔥 5개 선택 여부 확인 (버튼 클릭 시)
                if len(selected) != 5:
                    st.error(f"⚠️ 정확히 5개를 선택해주세요! (현재: {len(selected)}개)")
                    st.stop()  # 여기서 실행 중단
                
                # 🔥 user_id 확인
                if not st.session_state.onboarding_user_id:
                    st.error("❌ 사용자 ID가 없습니다. Step 1부터 다시 시작해주세요.")
                    st.session_state.onboarding_step = 1
                    st.rerun()
                
                # 5개 선택된 경우에만 API 호출
                with st.spinner("사용자 컨텍스트를 저장 중입니다..."):
                    try:
                        # 🔥 user_id 포함한 payload 구성
                        payload = {
                            "user_id": st.session_state.onboarding_user_id,
                            "name": st.session_state.onboarding_name,
                            "occupation": st.session_state.onboarding_occupation,
                            "selected_areas": selected
                        }
                        
                        # 디버깅용 출력 (선택사항)
                        with st.expander("🔍 전송 데이터 확인"):
                            st.json(payload)
                        
                        # API 호출: /api/onboarding/save-context
                        response = requests.post(
                            "http://127.0.0.1:8000/api/onboarding/save-context",
                            json=payload
                        )
                        
                        if response.status_code == 200:
                            result = response.json()
                            st.session_state.onboarding_user_id = result.get("user_id", "")
                            st.session_state.selected_areas = selected
                            st.session_state.onboarding_step = 3
                            st.success("✅ 온보딩이 완료되었습니다!")
                            st.balloons()  # 🎈 축하 애니메이션
                            st.rerun()
                        else:
                            st.error(f"❌ API 오류: {response.status_code}")
                            with st.expander("오류 상세 정보"):
                                st.code(response.text)
                                
                    except Exception as e:
                        st.error(f"❌ API 호출 실패: {e}")
                        st.exception(e)
            
            # 안내 메시지
            if len(selected) != 5:
                st.caption("💡 정확히 5개를 선택한 후 '완료' 버튼을 클릭하세요.")
    
    
    # ============================================
    # Step 3: 온보딩 완료
    # ============================================
    elif st.session_state.onboarding_step == 3:
        st.subheader("🎉 온보딩이 완료되었습니다!")
        
        st.success(f"**{st.session_state.onboarding_name}님**의 설정이 완료되었습니다.")
        
        # 사용자 정보 표시
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("이름", st.session_state.onboarding_name)
            st.metric("직업", st.session_state.onboarding_occupation)
        
        with col2:
            st.metric("User ID", st.session_state.onboarding_user_id[:12] + "...")
            st.metric("선택 영역", f"{len(st.session_state.selected_areas)}개")
        
        # 선택한 영역 표시
        st.divider()
        st.markdown("### 📋 선택한 관심 영역")
        
        for i, area in enumerate(st.session_state.selected_areas, 1):
            st.markdown(f"{i}. **{area}**")
        
        # 다시하기 버튼
        st.divider()
        
        if st.button("🔄 온보딩 다시하기", use_container_width=True):
            # 모든 온보딩 상태 초기화
            st.session_state.onboarding_step = 1
            st.session_state.onboarding_user_id = None
            st.session_state.onboarding_name = ""
            st.session_state.onboarding_occupation = ""
            st.session_state.suggested_areas = []
            st.session_state.selected_areas = []
            st.rerun()
        
        st.info("💡 이제 **Tab 2: 파일 분류**로 이동하여 문서를 업로드해보세요!")

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
            st.write(f" - {area}")
    
    uploaded_file = st.file_uploader(
        "분류할 파일 업로드", type=['pdf', 'txt', 'md'], key="file_uploader_tab2"
    )
    
    if uploaded_file:
        # 파일 정보 섹션 - 전체 너비
        st.markdown("### 📄 파일 정보")
        
        col1, col2, col3 = st.columns(3)  # 3등분은 유지하되
        with col1:
            st.metric("파일명", uploaded_file.name)
        with col2:
            st.metric("파일 크기", f"{uploaded_file.size / 1024:.2f} KB")
        with col3:
            st.metric("파일타입", uploaded_file.type.split('/')[-1].upper())

        # 구분선 추가
        st.divider()
        
        # 버튼 중앙 정렬하기
        _, col_center, _ = st.columns([1, 1, 1])
        with col_center:
            classify_btn = st.button(
                "🚀 분류 시작",
                key="classify_btn_tab2",
                use_container_width=True,       # 컬럼 너비에 맞춤
                type="primary"
            )
        # 분류 버튼 (API 호출 방식으로 변경!
        if classify_btn:
            with st.spinner("AI 분석 중... (사용자 맥락 반영)"):
                try:
                    # ============================================================
                    # 🔥 FastAPI /file 엔드포인트 호출 (완전 수정!)
                    # ============================================================
                    # 1. 파일 준비
                    file_bytes = uploaded_file.getvalue()
                    files = {
                        "file": (uploaded_file.name, file_bytes, uploaded_file.type)
                    }
                    
                    # 2. 데이터 준비 (form-data로 전송)
                    data = {
                        "user_id": st.session_state.onboarding_user_id,
                    }
                    
                    # 3. API 호출
                    response = requests.post(
                        "http://127.0.0.1:8000/api/classifier/file",
                        files=files,
                        data=data
                    )
                    
                    # 4. 응답 처리
                    if response.status_code == 200:
                        classification_result = response.json()
                        
                        # 5. 히스토리 저장
                        history_item = {
                            "filename": uploaded_file.name,
                            "category": classification_result.get('category', 'Unknown'),
                            "confidence": classification_result.get('confidence', 0),
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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
                        
                    else:
                        st.error(f"❌ API 오류: {response.status_code}")
                        st.code(response.text)
                    
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
st.caption("FlowNote MVP v3.5 | gpt-4o 선택 영역 확장 중 | Made with ❤️ by Jay")
