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
from datetime import datetime

# Backend 모듈 임포트
from backend.config import UPLOADS_DIR
from backend.utils import (
    get_timestamp,
    save_file,
    format_file_size,
    validate_file_extension
)

# 페이지 설정
st.set_page_config(
    page_title="FlowNote MVP",
    page_icon="📝",
    layout="wide"
)

# 제목
st.title("📝 FlowNote MVP")
st.markdown("**AI 대화를 체계적으로 저장하고 검색하세요**")

# 사이드바
with st.sidebar:
    st.header("⚙️ 설정")
    
    # 파일 통계
    if UPLOADS_DIR.exists():
        files = list(UPLOADS_DIR.glob("*"))
        file_count = len([f for f in files if f.is_file()])
        st.metric("업로드된 파일", file_count)
    else:
        st.metric("업로드된 파일", 0)
    
    st.divider()
    
    # 정보
    st.info("""
    **사용법**:
    1. AI 대화 파일 업로드 (.md, .txt)
    2. 키워드 검색
    3. 결과 요약 및 내보내기
    """)
    
    st.divider()
    
    # 버전 정보
    st.caption("FlowNote MVP v0.1.0")
    st.caption(f"Made with ❤️ by Jay Lee")

# 메인 영역
tab1, tab2, tab3 = st.tabs(["📤 업로드", "🔍 검색", "📊 관리"])

# ===================================
# Tab 1: 파일 업로드
# ===================================
with tab1:
    st.header("파일 업로드")
    
    uploaded_file = st.file_uploader(
        "AI 대화 파일을 업로드하세요",
        type=["md", "txt"],
        help="Markdown(.md) 또는 텍스트(.txt) 파일만 지원합니다"
    )
    
    if uploaded_file:
        # 파일 정보 표시
        st.success(f"✅ {uploaded_file.name} 업로드 완료!")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("파일명", uploaded_file.name)
        with col2:
            file_size_str = format_file_size(uploaded_file.size)
            st.metric("크기", file_size_str)
        
        # 미리보기
        with st.expander("📄 미리보기"):
            content = uploaded_file.read().decode("utf-8")
            st.text_area(
                "내용",
                content,
                height=200,
                disabled=True
            )
            uploaded_file.seek(0)  # 파일 포인터 리셋
        
        # 저장 버튼
        if st.button("💾 저장하기", type="primary"):
            try:
                # 타임스탬프 추가 (중복 방지)
                timestamp = get_timestamp()
                file_name = f"{timestamp}_{uploaded_file.name}"
                file_path = UPLOADS_DIR / file_name
                
                # 파일 저장
                content = uploaded_file.read().decode("utf-8")
                save_file(content, file_path)
                
                st.success(f"✅ {file_name}에 저장되었습니다!")
                st.balloons()
                
                # 저장 위치 안내
                st.info(f"📂 저장 위치: `{file_path}`")
                
            except Exception as e:
                st.error(f"❌ 저장 실패: {e}")

# ===================================
# Tab 2: 검색 (미구현)
# ===================================
with tab2:
    st.header("검색")
    st.info("🚧 검색 기능은 다음에 구현 예정입니다")
    
    # 검색 입력 (UI만)
    search_query = st.text_input(
        "검색어를 입력하세요",
        placeholder="예: 프로젝트 기획"
    )
    
    if st.button("🔍 검색", disabled=True):
        st.warning("아직 구현되지 않았습니다")

# ===================================
# Tab 3: 관리
# ===================================
with tab3:
    st.header("파일 관리")
    
    # 파일 목록 표시
    if UPLOADS_DIR.exists():
        files = sorted(
            [f for f in UPLOADS_DIR.glob("*") if f.is_file()],
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        
        if files:
            st.markdown(f"**총 {len(files)}개 파일**")
            
            for file in files:
                with st.expander(f"📄 {file.name}"):
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.text(f"크기: {format_file_size(file.stat().st_size)}")
                    
                    with col2:
                        modified_time = datetime.fromtimestamp(file.stat().st_mtime)
                        st.text(f"수정: {modified_time.strftime('%Y-%m-%d %H:%M')}")
                    
                    with col3:
                        if st.button("🗑️ 삭제", key=f"delete_{file.name}"):
                            file.unlink()
                            st.success(f"✅ {file.name} 삭제 완료!")
                            st.rerun()
        else:
            st.warning("업로드된 파일이 없습니다")
    else:
        st.warning("업로드된 파일이 없습니다")

# 푸터
st.divider()
st.markdown("""
<div style='text-align: center; color: gray; font-size: 0.9em;'>
    FlowNote MVP v0.1.0 | Made with ❤️ by Jay Lee
</div>
""", unsafe_allow_html=True)

