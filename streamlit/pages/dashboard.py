# frontend/pages/dashboard.py (수정)

import sys
from pathlib import Path

# 루트 폴더 경로 추가
root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root))

import streamlit as st
from streamlit_option_menu import option_menu
from backend.dashboard.dashboard_core import MetadataAggregator
from backend.metadata import FileMetadata
from backend.data_manager import DataManager
from backend.search_history import SearchHistory
from backend.database.connection import DatabaseConnection
import csv
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta
from wordcloud import WordCloud
import matplotlib.pyplot as plt
from st_aggrid import AgGrid


st.set_page_config(page_title="FlowNote Dashboard", layout="wide")

metadata_manager = FileMetadata()
all_files = metadata_manager.get_all_files()

# Step 1: CSS 스타일링 추가
# Step 1: CSS 스타일링 추가 (다크/라이트 모드 대응)
st.markdown("""
<style>
    /* 메트릭 카드 스타일 */
    [data-testid="stMetricValue"] {
        font-size: 32px;
        font-weight: bold;
    }
    
    [data-testid="stMetricLabel"] {
        font-size: 14px;
        font-weight: 600;
    }
    
    [data-testid="stMetricDelta"] {
        font-size: 14px;
    }
    
    /* 서브헤더 스타일 */
    h2, h3 {
        font-weight: 600 !important;
    }
    
    /* divider 스타일 */
    hr {
        border: none;
        border-top: 2px solid #dee2e6;
        margin: 20px 0;
    }
    
    /* 탭 스타일 - 기본(라이트 모드) */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 10px 20px;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    
    /* 라이트 모드 탭 스타일 */
    @media (prefers-color-scheme: light) {
        .stTabs [data-baseweb="tab"] {
            background-color: #f8f9fa;
            color: #2c3e50;
        }
        
        .stTabs [aria-selected="true"] {
            background-color: #3498db;
            color: white !important;
        }
        
        .stTabs [data-baseweb="tab"]:hover {
            background-color: #e9ecef;
            color: #2c3e50;
        }
        
        .stTabs [aria-selected="true"]:hover {
            background-color: #2980b9;
            color: white !important;
        }
    }
    
    /* 다크 모드 탭 스타일 */
    @media (prefers-color-scheme: dark) {
        .stTabs [data-baseweb="tab"] {
            background-color: #262730;
            color: #fafafa;
        }
        
        .stTabs [aria-selected="true"] {
            background-color: #3498db;
            color: white !important;
        }
        
        .stTabs [data-baseweb="tab"]:hover {
            background-color: #31333f;
            color: #fafafa;
        }
        
        .stTabs [aria-selected="true"]:hover {
            background-color: #2980b9;
            color: white !important;
        }
    }
</style>
""", unsafe_allow_html=True)


# =====================================
# 📊 실제 데이터 로드
# =====================================
@st.cache_data(ttl=60)  # 60초 캐시 (1분마다 갱신)
def load_dashboard_data():
    """
    대시보드 데이터 로드
    Returns:
        dict: 전체 파일 수, 총 검색 수, 분류율, 평균 중요도
    """
    try:
        # 1️⃣ FileMetadata에서 전체 파일 수 가져오기
        metadata_manager = FileMetadata()
        all_files = metadata_manager.get_all_files()
        total_files = len(all_files)
        
        # 2️⃣ classification_log.csv에서 분류 데이터 가져오기
        data_manager = DataManager()
        classifications_csv_path = data_manager.classifications_csv
        
        total_searches = 0
        completed_count = 0
        confidence_sum = 0
        confidence_count = 0
        
                # CSV 파일 읽기
        if classifications_csv_path.exists():
            with open(classifications_csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    total_searches += 1
                    
                    # 분류 완료 여부 확인
                    if row.get('user_selected'):
                        completed_count += 1
                    
                    # confidence 평균 계산
                    try:
                        confidence = float(row.get('confidence', 0))
                        if confidence > 0:
                            confidence_sum += confidence
                            confidence_count += 1
                    except:
                        pass
        # 3️⃣ 계산
        classification_rate = (completed_count / total_searches * 100) if total_searches > 0 else 0
        avg_confidence = (confidence_sum / confidence_count) if confidence_count > 0 else 0
        
        # 4️⃣ delta 계산 (이전 값과 비교 - 여기서는 임시로 +10 설정)
        prev_total_files = total_files - 12  # 임시
        prev_total_searches = total_searches - 8  # 임시
        
        delta_files = total_files - prev_total_files
        delta_searches_pct = ((total_searches - prev_total_searches) / prev_total_searches * 100) if prev_total_searches > 0 else 0
        
        return {
            "total_files": total_files,
            "delta_files": delta_files,
            "total_searches": total_searches,
            "delta_searches_pct": delta_searches_pct,
            "classification_rate": classification_rate,
            "avg_confidence": avg_confidence
        }
    except Exception as e:
        print(f"❌ 데이터 로드 실패: {e}")
        # 실패 시 기본값 반환
        return {
            "total_files": 0,
            "delta_files": 0,
            "total_searches": 0,
            "delta_searches_pct": 0,
            "classification_rate": 0,
            "avg_confidence": 0
        }

# 데이터 로드
dashboard_data = load_dashboard_data()

agg = MetadataAggregator()

@st.cache_data(ttl=60)
def load_para_distribution():
    """
    PARA 분포 데이터 로드
    Returns:
        pd.DataFrame: PARA 카테고리별 파일 개수
    """
    try:
        data_manager = DataManager()
        classifications_csv_path = data_manager.classifications_csv
        
        para_counts = {"Projects": 0, "Areas": 0, "Resources": 0, "Archives": 0}
        
        if classifications_csv_path.exists():
            with open(classifications_csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    para_category = row.get('user_selected', '').strip()
                    if para_category in para_counts:
                        para_counts[para_category] += 1
        
        # DataFrame 생성
        df = pd.DataFrame(list(para_counts.items()), columns=['PARA', 'Count'])
        return df
    
    except Exception as e:
        print(f"❌ PARA 분포 로드 실패: {e}")
        return pd.DataFrame({"PARA": ["Projects", "Areas", "Resources", "Archives"], "Count": [0, 0, 0, 0]})


@st.cache_data(ttl=60)
def load_search_trend():
    """
    최근 7일간 검색 트렌드 데이터 로드
    Returns:
        pd.DataFrame: 날짜별 검색 횟수
    """
    try:
        data_manager = DataManager()
        classifications_csv_path = data_manager.classifications_csv
        
        # 날짜별 검색 횟수 집계
        daily_counts = {}
        
        if classifications_csv_path.exists():
            with open(classifications_csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    timestamp = row.get('timestamp', '')
                    if timestamp:
                        try:
                            # 타임스탬프 파싱 (예: "20251110_044530_829" → "2025-11-10")
                            date_str = timestamp.split('_')[0]  # "20251110"
                            date_obj = datetime.strptime(date_str, "%Y%m%d")
                            date_key = date_obj.strftime("%Y-%m-%d")
                            daily_counts[date_key] = daily_counts.get(date_key, 0) + 1
                        except:
                            pass
        
        # 최근 7일 데이터만 필터링
        today = datetime.now()
        last_7_days = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
        
        trend_data = []
        for date in last_7_days:
            trend_data.append({"날짜": date, "검색 횟수": daily_counts.get(date, 0)})
        
        df = pd.DataFrame(trend_data)
        return df
    
    except Exception as e:
        print(f"❌ 검색 트렌드 로드 실패: {e}")
        return pd.DataFrame({"날짜": [], "검색 횟수": []})


@st.cache_data(ttl=60)
def load_stats_data():
    """
    통계 데이터를 CSV에서 로드하여 집계
    Returns:
        dict: 통계값들 (예: 전체 파일, 분류 완료 수 등)
    """
    try:
        data_manager = DataManager()
        classifications_csv_path = data_manager.classifications_csv
        
        total_files = 0
        classified_files = 0
        confidence_scores = []
        
        if classifications_csv_path.exists():
            with open(classifications_csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    total_files += 1
                    if row.get('user_selected'):
                        classified_files += 1
                    try:
                        conf = float(row.get('confidence', 0))
                        confidence_scores.append(conf)
                    except:
                        pass
        
        classification_rate = (classified_files / total_files * 100) if total_files else 0
        avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
        
        return {
            "total_files": total_files,
            "classified_files": classified_files,
            "classification_rate": classification_rate,
            "avg_confidence": avg_confidence
        }
    except Exception as e:
        print(f"❌ 통계 데이터 로드 실패: {e}")
        return {
            "total_files": 0,
            "classified_files": 0,
            "classification_rate": 0,
            "avg_confidence": 0
        }


@st.cache_data(ttl=60)
def load_recent_activities(limit: int = 10):
    """
    최근 분류 활동 로그를 CSV에서 최근 limit개 읽어 반환
    """
    try:
        data_manager = DataManager()
        classifications_csv_path = data_manager.classifications_csv
        
        logs = []
        if classifications_csv_path.exists():
            with open(classifications_csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                all_rows = list(reader)
                # 최신순으로 가장 최근 limit개 가져오기
                recent_rows = all_rows[-limit:]
                # 필요시 역순으로 줄 수도 있음
                for row in reversed(recent_rows):
                    logs.append({
                        "timestamp": row.get('timestamp', 'N/A'),
                        "title": row.get('title', '제목 없음'),
                        "user_selected": row.get('user_selected', '선택 없음'),
                        "confidence": row.get('confidence', '0')
                    })
        return logs
    except Exception as e:
        print(f"❌ 최근 활동 로드 실패: {e}")
        return []


@st.cache_data(ttl=60)
def load_file_list():
    from backend.metadata import FileMetadata
    metadata_manager = FileMetadata()
    files_dict = metadata_manager.get_all_files()
    files_list = [v for v in files_dict.values()]
    return pd.DataFrame(files_list)




@st.cache_data(ttl=60)
def build_file_tree():
    """
    파일 경로를 계층구조로 변환하여 트리 생성
    Returns:
        dict: 계층 구조로 파일 정보를 담은 트리
    """
    from backend.metadata import FileMetadata
    
    metadata_manager = FileMetadata()
    files_dict = metadata_manager.get_all_files()
    
    tree = {}
    for file_id, info in files_dict.items():
        filename = info.get('file_name', '')
        
        # 경로 없이 파일명만 있는 경우 root에 바로 저장
        if '/' not in filename and '\\' not in filename:
            tree[filename] = info
            continue
        
        # 경로 포함 파일은 계층 구조로 저장
        parts = filename.replace('\\', '/').split('/')
        current = tree
        
        # 폴더 경로 탐색
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            elif not isinstance(current[part], dict):
                # 충돌 방지: 파일과 폴더 이름이 같을 경우
                current[part] = {"__file__": current[part]}
            current = current[part]
        
        # 마지막 파일명 저장
        current[parts[-1]] = info
    
    return tree



@st.cache_data(ttl=60)
def load_recent_logs(n=10):
    data_manager = DataManager()
    classifications_csv_path = data_manager.classifications_csv
    records = []
    if classifications_csv_path.exists():
        df = pd.read_csv(classifications_csv_path)
        # 최근 n개 로그만
        records = df.sort_values('timestamp', ascending=False).head(n)
    return records


# ==============================
# 상단: KPI 메트릭 (실제 데이터)
# ==============================

st.header("📊 FlowNote Dashboard")

st.divider()

col1, col2, col3, col4 = st.columns(4)

# 📁 전체 파일
with col1:
    st.markdown("**📁 전체 파일**")
    metric_col1, metric_col2 = st.columns([3, 2], gap="small")
    
    with metric_col1:
        st.markdown(f"<h3 style='margin: 0; line-height: 1.2;'>{dashboard_data['total_files']}</h3>", 
                    unsafe_allow_html=True)
    
    with metric_col2:
        delta_val = dashboard_data['delta_files']
        if delta_val > 0:
            st.markdown(f"<div style='padding-top: 20px;'><span style='color: #09ab3b; font-size: 16px; font-weight: 600;'>▲ {delta_val:+d}개</span></div>", 
                        unsafe_allow_html=True)
        elif delta_val < 0:
            st.markdown(f"<div style='padding-top: 20px;'><span style='color: #ff4b4b; font-size: 16px; font-weight: 600;'>▼ {abs(delta_val)}개</span></div>", 
                        unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='padding-top: 20px;'><span style='color: #808495; font-size: 16px; font-weight: 600;'>― 0개</span></div>", 
                        unsafe_allow_html=True)

# 🔍 총 검색
with col2:
    st.markdown("**🔍 총 검색**")
    metric_col1, metric_col2 = st.columns([3, 2], gap="small")
    
    with metric_col1:
        st.markdown(f"<h3 style='margin: 0; line-height: 1.2;'>{dashboard_data['total_searches']}</h3>", 
                    unsafe_allow_html=True)
    
    with metric_col2:
        delta_val = dashboard_data['delta_searches_pct']
        if delta_val > 0:
            st.markdown(f"<div style='padding-top: 20px;'><span style='color: #09ab3b; font-size: 16px; font-weight: 600;'>▲ {delta_val:+.1f}%</span></div>", 
                        unsafe_allow_html=True)
        elif delta_val < 0:
            st.markdown(f"<div style='padding-top: 20px;'><span style='color: #ff4b4b; font-size: 16px; font-weight: 600;'>▼ {abs(delta_val):.1f}%</span></div>", 
                        unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='padding-top: 20px;'><span style='color: #808495; font-size: 16px; font-weight: 600;'>― 0.0%</span></div>", 
                        unsafe_allow_html=True)

# 📊 분류율
with col3:
    st.markdown("**📊 분류율**")
    metric_col1, metric_col2 = st.columns([3, 2], gap="small")
    
    with metric_col1:
        st.markdown(f"<h3 style='margin: 0; line-height: 1.2;'>{dashboard_data['classification_rate']:.1f}%</h3>", 
                    unsafe_allow_html=True)
    
    with metric_col2:
        # 임시 값 (나중에 이전 주와 비교)
        delta_val = 5.0
        if delta_val > 0:
            st.markdown(f"<div style='padding-top: 20px;'><span style='color: #09ab3b; font-size: 16px; font-weight: 600;'>▲ {delta_val:+.1f}%</span></div>", 
                        unsafe_allow_html=True)
        elif delta_val < 0:
            st.markdown(f"<div style='padding-top: 20px;'><span style='color: #ff4b4b; font-size: 16px; font-weight: 600;'>▼ {abs(delta_val):.1f}%</span></div>", 
                        unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='padding-top: 20px;'><span style='color: #808495; font-size: 16px; font-weight: 600;'>― 0.0%</span></div>", 
                        unsafe_allow_html=True)

# ⭐ 평균 신뢰도
with col4:
    st.markdown("**⭐ 평균 신뢰도**")
    metric_col1, metric_col2 = st.columns([3, 2], gap="small")
    
    with metric_col1:
        st.markdown(f"<h3 style='margin: 0; line-height: 1.2;'>{dashboard_data['avg_confidence']:.2f}</h3>", 
                    unsafe_allow_html=True)
    
    with metric_col2:
        # 임시 값
        delta_val = 0.05
        if delta_val > 0:
            st.markdown(f"<div style='padding-top: 20px;'><span style='color: #09ab3b; font-size: 16px; font-weight: 600;'>▲ {delta_val:+.2f}</span></div>", 
                        unsafe_allow_html=True)
        elif delta_val < 0:
            st.markdown(f"<div style='padding-top: 20px;'><span style='color: #ff4b4b; font-size: 16px; font-weight: 600;'>▼ {abs(delta_val):.2f}</span></div>", 
                        unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='padding-top: 20px;'><span style='color: #808495; font-size: 16px; font-weight: 600;'>― 0.00</span></div>", 
                        unsafe_allow_html=True)

#################################
# 중간: 키워드 클라우드
#################################

st.divider()

@st.cache_data(ttl=60)
def load_keyword_freq():
    # 예시: 키워드와 등장 빈도 딕셔너리 리턴
    return {
        'Python': 50,
        'Streamlit': 35,
        'Keyword': 20,
        'Cloud': 18,
        'Dashboard': 15,
        'PARA': 10,
        'Files': 8,
        'Classification': 5,
    }

st.subheader("🔍 키워드 클라우드")
keyword_freq = load_keyword_freq()
wc = WordCloud(width=400, height=200, background_color='white').generate_from_frequencies(keyword_freq)

fig, ax = plt.subplots(figsize=(8, 4))
ax.imshow(wc, interpolation='bilinear')
ax.axis('off')
st.pyplot(fig)



# ==============================
# 중앙 컬럼 - 2개
# ==============================

st.divider()

col_build_file_tree, col_table = st.columns([1, 1])

with col_build_file_tree:
    st.subheader("🏗️ 파일 트리")

    # 파일 트리 렌더링용 재귀 함수
    def render_file_tree(tree, indent=0, max_display=7):
        """
        트리 구조를 재귀적으로 Streamlit에 렌더링 (최대 7개까지만 표시)
        Args:
            tree (dict): 파일 트리 구조
            indent (int): 들여쓰기 레벨
            max_display (int): 최대 표시 개수
        """
        count = 0
        remaining_items = []
        
        for key, value in tree.items():
            if count < max_display:
                # 폴더인 경우
                if isinstance(value, dict) and 'file_name' not in value:
                    st.markdown("&nbsp;" * indent * 4 + f"📁 **{key}**")
                    render_file_tree(value, indent + 1, max_display=999)  # 하위 항목은 제한 없음
                # 파일인 경우
                else:
                    st.markdown("&nbsp;" * indent * 4 + f"📄 {key}")
                count += 1
            else:
                remaining_items.append((key, value))
        
        # 나머지 항목이 있으면 expander로 표시
        if remaining_items:
            with st.expander(f"... 외 {len(remaining_items)}개 더 보기"):
                for key, value in remaining_items:
                    if isinstance(value, dict) and 'file_name' not in value:
                        st.markdown("&nbsp;" * indent * 4 + f"📁 **{key}**")
                        render_file_tree(value, indent + 1, max_display=999)
                    else:
                        st.markdown("&nbsp;" * indent * 4 + f"📄 {key}")

    # 파일 트리를 실제로 화면에 표시
    file_tree = build_file_tree()
    
    if file_tree:
        render_file_tree(file_tree, max_display=7)
    else:
        st.info("불러온 파일이 없습니다.")




with col_table:
    st.subheader("📋 파일 목록")
    df_files = load_file_list()
    AgGrid(df_files)




# ==============================
# 하단 탭
# ==============================
st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["📈 검색 트렌드", "📊 PARA 분포", "🔥 최근 활동", "⚙️ 설정"])

with tab1:
    st.subheader("📈 최근 7일 검색 트렌드")
    
    # 검색 트렌드 데이터 로드
    trend_df = load_search_trend()
    
    if not trend_df.empty:
        # Plotly 라인 차트 생성
        fig = px.line(
            trend_df,
            x='날짜',
            y='검색 횟수',
            markers=True,
            labels={'검색 횟수': '검색 횟수', '날짜': '날짜'}
        )
        
        # 차트 레이아웃 설정
        fig.update_traces(
            line_color='#3498db',
            line_width=3,
            marker=dict(size=8, color='#3498db')
        )
        
        fig.update_layout(
            height=400,
            margin=dict(l=40, r=40, t=40, b=40),
            xaxis_title="날짜",
            yaxis_title="검색 횟수",
            hovermode='x unified'
        )
        
        st.plotly_chart(fig, width='stretch')
        
        # 통계 정보 표시
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("총 검색", f"{trend_df['검색 횟수'].sum()}회")
        with col2:
            st.metric("일평균", f"{trend_df['검색 횟수'].mean():.1f}회")
        with col3:
            st.metric("최대", f"{trend_df['검색 횟수'].max()}회")
    else:
        st.info("검색 트렌드 데이터가 없습니다.")

with tab2:
    st.subheader("📊 PARA 분포")
    
    # PARA 분포 데이터 로드
    para_df = load_para_distribution()
    
    # Plotly 바 차트 생성
    fig = px.bar(
        para_df,
        x='PARA',
        y='Count',
        text='Count',
        color='PARA',
        color_discrete_map={
            'Projects': '#e74c3c',      # 빨강
            'Areas': '#3498db',         # 파랑
            'Resources': '#2ecc71',     # 초록
            'Archives': '#95a5a6'       # 회색
        },
        labels={'Count': '파일 개수', 'PARA': 'PARA 카테고리'}
    )
    
    # 차트 레이아웃 설정
    fig.update_traces(textposition='outside')
    fig.update_layout(
        showlegend=False,
        height=300,
        margin=dict(l=20, r=20, t=20, b=20),
        xaxis_title="",
        yaxis_title="파일 개수"
    )
    
    st.plotly_chart(fig, width='stretch')

with tab3:
    st.subheader("🔥 최근 활동 로그")
    recent_logs = load_recent_activities(limit=10)
    if recent_logs:
        for log in recent_logs:
            st.write(f"- ⏰ {log['timestamp']} | 📄 {log['title']} | ✅ 선택: {log['user_selected']} | 🎯 신뢰도: {log['confidence']}")
    else:
        st.info("최근 활동 로그가 없습니다.")


# tab4 설정 탭 내용 (dashboard.py의 with tab4: 부분을 대체)
with tab4:
    st.subheader("⚙️ 대시보드 설정")
    
    # 두 개의 컬럼으로 나누기 (gap 추가)
    settings_col1, settings_col2 = st.columns(2, gap="large")
    
    # ===== 왼쪽 컬럼: 데이터 관리 =====
    with settings_col1:
        st.markdown("### 📊 데이터 관리")
        
        # 캐시 새로고침
        if st.button("🔄 캐시 새로고침", width='stretch'):
            st.cache_data.clear()
            st.success("✅ 캐시가 성공적으로 새로고침되었습니다!")
            st.rerun()
        
        st.markdown("---")
        
        # 데이터 내보내기
        st.markdown("#### 📤 데이터 내보내기")
        export_format = st.selectbox(
            "내보내기 형식",
            ["CSV", "JSON", "Excel"],
            key="export_format"
        )
        
        if st.button("💾 분류 데이터 내보내기", width='stretch'):
            try:
                data_manager = DataManager()
                classifications_csv_path = data_manager.classifications_csv
                
                if classifications_csv_path.exists():
                    if export_format == "CSV":
                        with open(classifications_csv_path, 'r', encoding='utf-8') as f:
                            csv_data = f.read()
                        st.download_button(
                            label="⬇️ CSV 다운로드",
                            data=csv_data,
                            file_name=f"classifications_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv",
                            width='stretch'
                        )
                    elif export_format == "JSON":
                        import json
                        with open(classifications_csv_path, 'r', encoding='utf-8') as f:
                            reader = csv.DictReader(f)
                            data = list(reader)
                        json_data = json.dumps(data, ensure_ascii=False, indent=2)
                        st.download_button(
                            label="⬇️ JSON 다운로드",
                            data=json_data,
                            file_name=f"classifications_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                            mime="application/json",
                            width='stretch'
                        )
                else:
                    st.warning("⚠️ 내보낼 데이터가 없습니다.")
            except Exception as e:
                st.error(f"❌ 내보내기 실패: {e}")
        
        st.markdown("---")
    
        # 데이터베이스 초기화 (위험한 작업이므로 확인 절차 추가)
        st.markdown("#### ⚠️ 위험 구역")
        with st.expander("🗑️ 데이터베이스 초기화", expanded=False):
            st.warning("⚠️ 이 작업은 모든 분류 데이터를 삭제합니다. 복구할 수 없습니다!")
            
            confirm_text = st.text_input(
                "초기화하려면 'DELETE'를 입력하세요:",
                key="confirm_delete"
            )
            
            if st.button("🗑️ 영구 삭제", type="primary", width='stretch'):
                if confirm_text == "DELETE":
                    try:
                        data_manager = DataManager()
                        classifications_csv_path = data_manager.classifications_csv
                        
                        # 백업 생성
                        if classifications_csv_path.exists():
                            backup_path = classifications_csv_path.parent / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                            import shutil
                            shutil.copy(classifications_csv_path, backup_path)
                            st.info(f"ℹ️ 백업 생성: {backup_path.name}")
                        
                        # 파일 초기화 (헤더만 남김)
                        with open(classifications_csv_path, 'w', encoding='utf-8') as f:
                            f.write("timestamp,title,query,selected_category,user_selected,confidence,feedback\n")
                        
                        st.success("✅ 데이터베이스가 초기화되었습니다!")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 초기화 실패: {e}")
                else:
                    st.error("❌ 'DELETE'를 정확히 입력해주세요.")
    
    # ===== 오른쪽 컬럼: 표시 설정 및 시스템 정보 =====
    with settings_col2:
        st.markdown("### 🎨 표시 설정")
        
        # 대시보드 새로고침 주기
        refresh_interval = st.select_slider(
            "대시보드 새로고침 주기 (초)",
            options=[30, 60, 120, 300, 600],
            value=60,
            key="refresh_interval"
        )
        st.info(f"ℹ️ 현재 캐시 TTL: {refresh_interval}초")
        
        # 데이터 표시 범위
        data_range = st.radio(
            "데이터 표시 범위",
            ["최근 7일", "최근 30일", "최근 90일", "전체"],
            index=0,
            key="data_range"
        )
        
        st.markdown("---")
        
        # 차트 색상 테마
        st.markdown("#### 🎨 차트 색상 테마")
        color_theme = st.selectbox(
            "색상 테마 선택",
            ["기본 (파랑/빨강/초록)", "파스텔", "다크 모드", "모노크롬"],
            key="color_theme"
        )
        
        if color_theme != "기본 (파랑/빨강/초록)":
            st.info(f"ℹ️ '{color_theme}' 테마가 다음 새로고침에 적용됩니다.")
    
    # ===== 구분선 =====
    st.divider()
    
    # ===== 하단: 시스템 정보와 버전 정보를 3단으로 나누기 (중앙 세로 구분선 추가) =====
    col_system_info, col_divider, col_version_info = st.columns([5, 0.5, 5])
    
    with col_system_info:
        # 시스템 정보
        st.markdown("### 💻 시스템 정보")
        
        try:
            data_manager = DataManager()
            classifications_csv_path = data_manager.classifications_csv
            
            # 파일 크기
            if classifications_csv_path.exists():
                file_size = classifications_csv_path.stat().st_size
                file_size_mb = file_size / (1024 * 1024)
                
                # 마지막 수정 시간
                last_modified = datetime.fromtimestamp(classifications_csv_path.stat().st_mtime)
                
                # 레코드 수
                with open(classifications_csv_path, 'r', encoding='utf-8') as f:
                    record_count = sum(1 for _ in f) - 1  # 헤더 제외
                
                # 정보 표시
                info_col1, info_col2 = st.columns(2)
                
                with info_col1:
                    st.metric("📁 데이터베이스 크기", f"{file_size_mb:.2f} MB")
                    st.metric("📊 총 레코드 수", f"{record_count:,}개")
                
                with info_col2:
                    st.metric("🕐 마지막 업데이트", last_modified.strftime("%Y-%m-%d"))
                    st.metric("⏱️ 시간", last_modified.strftime("%H:%M:%S"))
                
                # 데이터베이스 상태
                if file_size_mb < 10:
                    status = "🟢 정상"
                    status_color = "green"
                elif file_size_mb < 50:
                    status = "🟡 주의"
                    status_color = "orange"
                else:
                    status = "🔴 경고 (최적화 필요)"
                    status_color = "red"
                
                st.markdown(f"**데이터베이스 상태:** :{status_color}[{status}]")
                
            else:
                st.warning("⚠️ 데이터베이스 파일을 찾을 수 없습니다.")
                
        except Exception as e:
            st.error(f"❌ 시스템 정보 로드 실패: {e}")
    
    # 중앙 세로 구분선
    with col_divider:
        st.markdown(
            """
            <div style="
                height: 100%;
                min-height: 300px;
                border-left: 2px solid #dee2e6;
                margin: 0 auto;
            "></div>
            """,
            unsafe_allow_html=True
        )
    
    with col_version_info:
        # 버전 정보
        st.markdown("### 📦 버전 정보")
        st.text("FlowNote Dashboard v3.5.0")
        st.text("Streamlit " + st.__version__)
        st.text(f"Python {sys.version.split()[0]}")