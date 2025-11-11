# streamlit/test_ui4.py
"""
FlowNote 통합 UI - 온보딩 플로우 추가
- Tab 1: 파일 업로드 & 분류 (기존)
- Tab 2: 메타데이터 확인 (기존)
- Tab 3: 분류 통계 (기존)
- Tab 4: 온보딩 플로우 (신규)
"""
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

# Backend 임포트
from backend.classifier.para_agent_wrapper import run_para_agent_sync
from backend.database.metadata_schema import ClassificationMetadataExtender
from backend.database.connection import DatabaseConnection
from backend.utils import load_pdf

# 페이지 설정
st.set_page_config(
    page_title="FlowNote 통합 테스트",
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

# 타이틀
st.title("📚 FlowNote 통합 테스트 UI")
st.markdown("**파일 업로드 → LangChain 분류 → 메타데이터 확인 → 온보딩 플로우**")

# 사이드바
with st.sidebar:
    st.header("📊 분류 히스토리")
    
    if st.session_state.classification_history:
        st.metric("총 분류 파일", len(st.session_state.classification_history))
        
        with st.expander("🗂️ 최근 분류 결과", expanded=True):
            for idx, item in enumerate(reversed(st.session_state.classification_history[-5:]), 1):
                st.markdown(f"**{idx}. {item['filename']}**")
                st.caption(f"카테고리: {item['category']} ({item['confidence']:.0%})")
                st.caption(f"시간: {item['timestamp']}")
                st.divider()
        
        if st.button("🗑️ 히스토리 초기화", key="clear_history"):
            st.session_state.classification_history = []
            st.rerun()
    else:
        st.info("아직 분류된 파일이 없습니다")

# 메인 영역
tab1, tab2, tab3, tab4 = st.tabs([
    "📤 파일 업로드 & 분류",
    "📊 메타데이터 확인",
    "🎯 분류 통계",
    "🚀 온보딩 플로우"
])

# ============================================================================
# TAB 1: 파일 업로드 & 분류 (기존)
# ============================================================================
with tab1:
    st.header("📤 파일 업로드 & 자동 분류")
    
    uploaded_file = st.file_uploader(
        "분류할 파일을 업로드하세요",
        type=['pdf', 'txt', 'md'],
        help="PDF, TXT, MD 파일을 지원합니다",
        key="file_uploader_tab1"
    )
    
    if uploaded_file:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("파일명", uploaded_file.name)
        with col2:
            st.metric("파일 크기", f"{uploaded_file.size / 1024:.2f} KB")
        with col3:
            st.metric("파일 타입", uploaded_file.type.split('/')[-1].upper())
        
        if st.button("🚀 분류 시작", type="primary", key="classify_btn_tab1"):
            with st.spinner("🤖 AI가 파일을 분석하고 있습니다..."):
                try:
                    if uploaded_file.type == "application/pdf":
                        text = load_pdf(uploaded_file)
                    else:
                        text = uploaded_file.read().decode('utf-8')
                    
                    metadata = {
                        "filename": uploaded_file.name,
                        "file_size": uploaded_file.size,
                        "file_type": uploaded_file.type,
                        "uploaded_at": datetime.now().isoformat()
                    }
                    
                    classification_result = run_para_agent_sync(
                        text=text[:2000],
                        metadata=metadata
                    )
                    
                    file_id = st.session_state.db_extender.save_classification_result(
                        result=classification_result,
                        filename=uploaded_file.name
                    )
                    
                    history_item = {
                        "filename": uploaded_file.name,
                        "category": classification_result.get('category', 'Unknown'),
                        "confidence": classification_result.get('confidence', 0),
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "file_id": file_id
                    }
                    st.session_state.classification_history.append(history_item)
                    
                    st.success("✅ 분류 완료!")
                    
                    st.markdown("---")
                    st.subheader("📊 분류 결과")
                    
                    category_icons = {
                        "Projects": "🚀",
                        "Areas": "🎯",
                        "Resources": "📚",
                        "Archives": "📦"
                    }
                    
                    category = classification_result.get('category', 'Unknown')
                    icon = category_icons.get(category, "❓")
                    
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        st.markdown(f"### {icon} {category}")
                        st.progress(classification_result.get('confidence', 0))
                        st.caption(f"신뢰도: {classification_result.get('confidence', 0):.0%}")
                    
                    with col2:
                        if classification_result.get('conflict_detected', False):
                            st.warning("⚠️ 충돌 감지됨")
                        else:
                            st.success("✅ 명확한 분류")
                        
                        if classification_result.get('requires_review', False):
                            st.info("👀 검토 필요")
                    
                    with st.expander("📝 분류 근거", expanded=True):
                        st.markdown(classification_result.get('reasoning', '정보 없음'))
                    
                    with st.expander("🔑 키워드 태그"):
                        tags = classification_result.get('keyword_tags', [])
                        if tags:
                            st.write(", ".join([f"`{tag}`" for tag in tags[:10]]))
                        else:
                            st.caption("키워드 없음")
                    
                    with st.expander("📋 메타데이터"):
                        st.json({
                            "filename": uploaded_file.name,
                            "file_size_kb": f"{uploaded_file.size / 1024:.2f}",
                            "file_type": uploaded_file.type,
                            "classified_at": datetime.now().isoformat(),
                            "file_id": file_id
                        })
                    
                except Exception as e:
                    st.error(f"❌ 분류 실패: {str(e)}")
                    st.exception(e)

# ============================================================================
# TAB 2: 메타데이터 확인 (기존)
# ============================================================================
with tab2:
    st.header("📊 저장된 메타데이터 확인")
    
    try:
        all_classifications = st.session_state.db_extender.get_all_classifications()
        
        if all_classifications:
            st.metric("저장된 분류 결과", len(all_classifications))
            
            import pandas as pd
            
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
            
            df = pd.DataFrame(df_data)
            st.dataframe(df, width='content')
            
            st.subheader("🔍 상세 정보")
            selected_file = st.selectbox(
                "파일 선택",
                options=[item['filename'] for item in all_classifications],
                key="file_select_tab2"
            )
            
            if selected_file:
                selected_item = next(
                    (item for item in all_classifications if item['filename'] == selected_file),
                    None
                )
                
                if selected_item:
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("**기본 정보**")
                        st.write(f"파일명: {selected_item['filename']}")
                        st.write(f"카테고리: {selected_item['para_category']}")
                        st.write(f"신뢰도: {selected_item['confidence_score']:.0%}")
                    
                    with col2:
                        st.markdown("**분류 상태**")
                        st.write(f"충돌 감지: {'예' if selected_item['conflict_flag'] else '아니오'}")
                        st.write(f"해결 방법: {selected_item['resolution_method'][:50]}")
                    
                    st.markdown("**키워드 태그**")
                    st.code(selected_item['keyword_tags'] if selected_item['keyword_tags'] else "없음")
        else:
            st.info("저장된 메타데이터가 없습니다. TAB 1에서 파일을 업로드하세요.")
    
    except Exception as e:
        st.error(f"메타데이터 로드 실패: {str(e)}")

# ============================================================================
# TAB 3: 분류 통계 (기존)
# ============================================================================
with tab3:
    st.header("🎯 분류 통계")
    
    if st.session_state.classification_history:
        from collections import Counter
        
        categories = [item['category'] for item in st.session_state.classification_history]
        category_counts = Counter(categories)
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("🚀 Projects", category_counts.get('Projects', 0))
        with col2:
            st.metric("🎯 Areas", category_counts.get('Areas', 0))
        with col3:
            st.metric("📚 Resources", category_counts.get('Resources', 0))
        with col4:
            st.metric("📦 Archives", category_counts.get('Archives', 0))
        
        st.subheader("📊 신뢰도 분포")
        confidences = [item['confidence'] for item in st.session_state.classification_history]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0
        
        st.metric("평균 신뢰도", f"{avg_confidence:.0%}")
        
        st.bar_chart(category_counts)
        
    else:
        st.info("분류된 파일이 없습니다. TAB 1에서 파일을 업로드하세요.")

# ============================================================================
# TAB 4: 온보딩 플로우 (신규)
# ============================================================================
with tab4:
    st.header("🚀 온보딩 플로우")
    st.markdown("**사용자 맞춤 영역 설정**")
    
    # Step 1: 직업 입력
    if st.session_state.onboarding_step == 1:
        st.subheader("Step 1: 기본 정보 입력")
        
        with st.form("step1_form"):
            name = st.text_input(
                "이름",
                value=st.session_state.onboarding_name,
                placeholder="예: Jay",
                help="닉네임 또는 실명을 입력하세요"
            )
            
            occupation = st.text_input(
                "직업",
                value=st.session_state.onboarding_occupation,
                placeholder="예: 교사, 개발자, 디자이너",
                help="현재 직업을 입력하세요"
            )
            
            submitted = st.form_submit_button("다음 단계로 →", type="primary", width='content')
            
            if submitted:
                if not name or not occupation:
                    st.error("⚠️ 이름과 직업을 모두 입력해주세요")
                else:
                    # 사용자 ID 생성 (실제로는 백엔드 API 호출)
                    import uuid
                    user_id = f"user_{uuid.uuid4().hex[:8]}"
                    
                    st.session_state.onboarding_user_id = user_id
                    st.session_state.onboarding_name = name
                    st.session_state.onboarding_occupation = occupation
                    
                    # GPT-4o로 영역 추천 (실제로는 백엔드 API 호출)
                    # 여기서는 더미 데이터로 대체
                    if occupation.lower() in ["교사", "선생님", "teacher"]:
                        st.session_state.suggested_areas = [
                            "수업 계획 및 준비",
                            "학생 평가 관리",
                            "교실 관리",
                            "상담 지도",
                            "교과 연구"
                        ]
                    elif occupation.lower() in ["개발자", "프로그래머", "developer"]:
                        st.session_state.suggested_areas = [
                            "코드 리뷰",
                            "프로젝트 관리",
                            "기술 문서 작성",
                            "버그 수정",
                            "새로운 기술 학습"
                        ]
                    elif occupation.lower() in ["디자이너", "designer"]:
                        st.session_state.suggested_areas = [
                            "UI/UX 디자인",
                            "브랜딩 작업",
                            "디자인 시스템 구축",
                            "클라이언트 미팅",
                            "트렌드 리서치"
                        ]
                    else:
                        st.session_state.suggested_areas = [
                            "업무 계획",
                            "프로젝트 관리",
                            "문서 작성",
                            "회의 및 협업",
                            "자기 계발"
                        ]
                    
                    st.session_state.onboarding_step = 2
                    st.success(f"✅ {name}님, 환영합니다!")
                    st.rerun()
    
    # Step 2: 영역 선택
    elif st.session_state.onboarding_step == 2:
        st.subheader("Step 2: 관심 영역 선택")
        
        st.info(f"👤 **{st.session_state.onboarding_name}**님 ({st.session_state.onboarding_occupation})")
        st.markdown("**GPT-4o가 추천한 핵심 영역입니다:**")
        
        st.markdown("---")
        
        # 영역 선택 (체크박스)
        for area in st.session_state.suggested_areas:
            if st.checkbox(area, key=f"area_{area}"):
                if area not in st.session_state.selected_areas:
                    st.session_state.selected_areas.append(area)
            else:
                if area in st.session_state.selected_areas:
                    st.session_state.selected_areas.remove(area)
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("← 이전 단계", width='content'):
                st.session_state.onboarding_step = 1
                st.rerun()
        
        with col2:
            if st.button(
                "저장하고 시작하기 →",
                type="primary",
                width='content',
                disabled=(len(st.session_state.selected_areas) == 0)
            ):
                if len(st.session_state.selected_areas) == 0:
                    st.warning("⚠️ 최소 1개 이상의 영역을 선택해주세요")
                else:
                    # 실제로는 백엔드 API 호출하여 저장
                    st.session_state.onboarding_step = 3
                    st.rerun()
        
        if len(st.session_state.selected_areas) > 0:
            st.caption(f"선택된 영역: {len(st.session_state.selected_areas)}개")
    
    # Step 3: 완료
    elif st.session_state.onboarding_step == 3:
        st.subheader("🎉 온보딩 완료!")
        
        st.success(f"**{st.session_state.onboarding_name}**님의 맞춤 설정이 완료되었습니다!")
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.markdown("### 📋 설정 요약")
            st.write(f"**이름:** {st.session_state.onboarding_name}")
            st.write(f"**직업:** {st.session_state.onboarding_occupation}")
            st.write(f"**사용자 ID:** {st.session_state.onboarding_user_id}")
        
        with col2:
            st.markdown("### 🎯 선택한 영역")
            for idx, area in enumerate(st.session_state.selected_areas, 1):
                st.write(f"{idx}. {area}")
        
        st.markdown("---")
        
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            if st.button("🏠 대시보드로 이동", type="primary", width='content'):
                st.info("💡 대시보드 기능은 개발 중입니다")
        
        with col_btn2:
            if st.button("🔄 온보딩 다시 하기", width='content'):
                # 세션 초기화
                st.session_state.onboarding_step = 1
                st.session_state.onboarding_user_id = None
                st.session_state.onboarding_name = ""
                st.session_state.onboarding_occupation = ""
                st.session_state.suggested_areas = []
                st.session_state.selected_areas = []
                st.rerun()

# 하단 정보
st.divider()
st.caption("FlowNote MVP v3.1 | LangChain + LangGraph 통합 | Made with ❤️ by Jay")
