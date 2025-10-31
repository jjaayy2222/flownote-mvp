# frontend/pages/dashboard.py (수정)

import streamlit as st
from streamlit_option_menu import option_menu
from backend.dashboard.dashboard_core import MetadataAggregator

st.set_page_config(page_title="FlowNote Dashboard", layout="wide")

agg = MetadataAggregator()

# 상단: KPI 메트릭
st.subheader("📊 FlowNote Dashboard")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("📁 전체 파일", 461)

with col2:
    st.metric("🔍 총 검색", 157)

with col3:
    st.metric("📊 분류율", "75%")

with col4:
    st.metric("⭐ 평균 중요도", "7.5/10")

# 중앙: 3컬럼 레이아웃
st.divider()

col_tree, col_table, col_chart = st.columns([1, 2, 1.5])

with col_tree:
    st.subheader("📁 파일 트리")
    st.info("파일 구조 (나중에 트리 디렉토리 추가)")

with col_table:
    st.subheader("📋 파일 목록")
    st.info("테이블 (streamlit-aggrid 연동)")

with col_chart:
    st.subheader("📊 PARA 분포")
    st.info("차트 (Plotly 연동)")

# 하단: 탭
st.divider()

tab1, tab2, tab3 = st.tabs(["📈 검색 트렌드", "🔥 활동", "📸 스냅샷"])

with tab1:
    st.info("검색 트렌드 차트")

with tab2:
    st.info("활동 히트맵")

with tab3:
    st.info("스냅샷 비교")
