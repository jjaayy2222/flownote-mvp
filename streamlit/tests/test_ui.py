# steamlit/app_integrated.py
"""
FlowNote 통합 UI - 파일 업로드 → LangChain 분류 → 메타데이터 표시
"""

import os
import sys
from pathlib import Path

# 프로젝트 루트 경로 추가 (중요!!!)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

# 두 번째: Streamlit + 환경변수 로드
import streamlit as st

# 로컬에서는 .env 로드
load_dotenv()

# 세 번쩨: 배포 환경에서는 Streamlit Secrets 로드
# 배포에서는 Streamlit Secrets → 환경변수 동기화
# (로컬에서는 st.secrets 접근하지 않음)
try:
    if hasattr(st, "secrets") and len(st.secrets) > 0:
        for key in [
            "EMBEDDING_API_KEY",
            "EMBEDDING_BASE_URL",
            "EMBEDDING_MODEL",
            "EMBEDDING_LARGE_API_KEY",
            "EMBEDDING_LARGE_BASE_URL",
            "EMBEDDING_LARGE_MODEL",
            "GPT4O_API_KEY",
            "GPT4O_BASE_URL",
            "GPT4O_MODEL",
            "GPT4O_MINI_API_KEY",
            "GPT4O_MINI_BASE_URL",
            "GPT4O_MINI_MODEL",
            "GPT41_API_KEY",
            "GPT41_BASE_URL",
            "GPT41_MODEL",
        ]:
            if key in st.secrets:
                os.environ[key] = st.secrets[key]
except:
    # Secrets 파일 없음 = 로컬 개발 환경
    # .env에서 로드된 변수 사용
    pass


import json
from datetime import datetime

# 네 번쩨: 다음 임포트
from backend.classifier.para_agent_wrapper import run_para_agent_sync
from backend.database.connection import DatabaseConnection
from backend.database.metadata_schema import ClassificationMetadataExtender
from backend.utils import load_pdf

# 페이지 설정
st.set_page_config(page_title="FlowNote 통합 테스트", page_icon="📚", layout="wide")

# 세션 상태 초기화
if "classification_history" not in st.session_state:
    st.session_state.classification_history = []

if "db_extender" not in st.session_state:
    st.session_state.db_extender = ClassificationMetadataExtender()

# 타이틀
st.title("📚 FlowNote 통합 테스트 UI")
st.markdown("**파일 업로드 → LangChain 분류 → 메타데이터 확인**")

# 사이드바 - 분류 히스토리
with st.sidebar:
    st.header("📊 분류 히스토리")

    if st.session_state.classification_history:
        st.metric("총 분류 파일", len(st.session_state.classification_history))

        with st.expander("🗂️ 최근 분류 결과", expanded=True):
            for idx, item in enumerate(
                reversed(st.session_state.classification_history[-5:]), 1
            ):
                st.markdown(f"**{idx}. {item['filename']}**")
                st.caption(f"카테고리: {item['category']} ({item['confidence']:.0%})")
                st.caption(f"시간: {item['timestamp']}")
                st.divider()

        if st.button("🗑️ 히스토리 초기화", width="stretch"):
            st.session_state.classification_history = []
            st.rerun()
    else:
        st.info("아직 분류된 파일이 없습니다")

# 메인 영역
tab1, tab2, tab3 = st.tabs(
    [
        "📤 파일 업로드 & 분류",  # 기존
        "📊 메타데이터 확인",  # 기존
        "🎯 분류 통계",  # 기존
    ]
)

# ============================================================================
# TAB 1: 파일 업로드 & 분류
# ============================================================================
with tab1:
    st.header("📤 파일 업로드 & 자동 분류")

    uploaded_file = st.file_uploader(
        "분류할 파일을 업로드하세요",
        type=["pdf", "txt", "md"],
        help="PDF, TXT, MD 파일을 지원합니다",
    )

    if uploaded_file:
        # 파일 정보 표시
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("파일명", uploaded_file.name)
        with col2:
            st.metric("파일 크기", f"{uploaded_file.size / 1024:.2f} KB")
        with col3:
            st.metric("파일 타입", uploaded_file.type.split("/")[-1].upper())

        # 분류 버튼
        if st.button("🚀 분류 시작", type="primary", width="stretch"):
            with st.spinner("🤖 AI가 파일을 분석하고 있습니다..."):
                try:
                    # 1. 파일 읽기
                    if uploaded_file.type == "application/pdf":
                        text = load_pdf(uploaded_file)
                    else:
                        text = uploaded_file.read().decode("utf-8")

                    # 2. 메타데이터 구성
                    metadata = {
                        "filename": uploaded_file.name,
                        "file_size": uploaded_file.size,
                        "file_type": uploaded_file.type,
                        "uploaded_at": datetime.now().isoformat(),
                    }

                    # 3. LangChain + LangGraph 기반 분류
                    classification_result = run_para_agent_sync(
                        text=text[:2000], metadata=metadata  # 처음 2000자만 사용
                    )

                    # 4. 데이터베이스 저장
                    file_id = st.session_state.db_extender.save_classification_result(
                        result=classification_result, filename=uploaded_file.name
                    )

                    # 5. 히스토리 저장
                    history_item = {
                        "filename": uploaded_file.name,
                        "category": classification_result.get("category", "Unknown"),
                        "confidence": classification_result.get("confidence", 0),
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "file_id": file_id,
                    }
                    st.session_state.classification_history.append(history_item)

                    st.success("✅ 분류 완료!")

                    # 6. 결과 표시
                    st.markdown("---")
                    st.subheader("📊 분류 결과")

                    # 카테고리 아이콘
                    category_icons = {
                        "Projects": "🚀",
                        "Areas": "🎯",
                        "Resources": "📚",
                        "Archives": "📦",
                    }

                    category = classification_result.get("category", "Unknown")
                    icon = category_icons.get(category, "❓")

                    # 결과 카드
                    col1, col2 = st.columns([2, 1])

                    with col1:
                        st.markdown(f"### {icon} {category}")
                        st.progress(classification_result.get("confidence", 0))
                        st.caption(
                            f"신뢰도: {classification_result.get('confidence', 0):.0%}"
                        )

                    with col2:
                        if classification_result.get("conflict_detected", False):
                            st.warning("⚠️ 충돌 감지됨")
                        else:
                            st.success("✅ 명확한 분류")

                        if classification_result.get("requires_review", False):
                            st.info("👀 검토 필요")

                    # 상세 정보
                    with st.expander("📝 분류 근거", expanded=True):
                        st.markdown(classification_result.get("reasoning", "정보 없음"))

                    with st.expander("🔑 키워드 태그"):
                        tags = classification_result.get("keyword_tags", [])
                        if tags:
                            st.write(", ".join([f"`{tag}`" for tag in tags[:10]]))
                        else:
                            st.caption("키워드 없음")

                    # 메타데이터 표시
                    with st.expander("📋 메타데이터"):
                        st.json(
                            {
                                "filename": uploaded_file.name,
                                "file_size_kb": f"{uploaded_file.size / 1024:.2f}",
                                "file_type": uploaded_file.type,
                                "classified_at": datetime.now().isoformat(),
                                "file_id": file_id,
                            }
                        )

                except Exception as e:
                    st.error(f"❌ 분류 실패: {str(e)}")
                    st.exception(e)

# ============================================================================
# TAB 2: 메타데이터 확인
# ============================================================================
with tab2:
    st.header("📊 저장된 메타데이터 확인")

    # 데이터베이스에서 모든 분류 결과 가져오기
    try:
        all_classifications = st.session_state.db_extender.get_all_classifications()

        if all_classifications:
            st.metric("저장된 분류 결과", len(all_classifications))

            # 데이터프레임 표시
            import pandas as pd

            df_data = []
            for item in all_classifications:
                df_data.append(
                    {
                        "파일명": item["filename"],
                        "카테고리": item["para_category"],
                        "신뢰도": f"{item['confidence_score']:.0%}",
                        "키워드": (
                            item["keyword_tags"][:50] if item["keyword_tags"] else ""
                        ),
                        "충돌": "⚠️" if item["conflict_flag"] else "✅",
                        "Snapshot ID": (
                            item["snapshot_id"][:20] if item["snapshot_id"] else ""
                        ),
                    }
                )

            df = pd.DataFrame(df_data)
            st.dataframe(df, width="stretch")

            # 상세 보기
            st.subheader("🔍 상세 정보")
            selected_file = st.selectbox(
                "파일 선택", options=[item["filename"] for item in all_classifications]
            )

            if selected_file:
                selected_item = next(
                    (
                        item
                        for item in all_classifications
                        if item["filename"] == selected_file
                    ),
                    None,
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
                        st.write(
                            f"충돌 감지: {'예' if selected_item['conflict_flag'] else '아니오'}"
                        )
                        st.write(
                            f"해결 방법: {selected_item['resolution_method'][:50]}"
                        )

                    st.markdown("**키워드 태그**")
                    st.code(
                        selected_item["keyword_tags"]
                        if selected_item["keyword_tags"]
                        else "없음"
                    )
        else:
            st.info("저장된 메타데이터가 없습니다. TAB 1에서 파일을 업로드하세요.")

    except Exception as e:
        st.error(f"메타데이터 로드 실패: {str(e)}")

# ============================================================================
# TAB 3: 분류 통계
# ============================================================================
with tab3:
    st.header("🎯 분류 통계")

    if st.session_state.classification_history:
        # 카테고리별 통계
        from collections import Counter

        categories = [
            item["category"] for item in st.session_state.classification_history
        ]
        category_counts = Counter(categories)

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("🚀 Projects", category_counts.get("Projects", 0))
        with col2:
            st.metric("🎯 Areas", category_counts.get("Areas", 0))
        with col3:
            st.metric("📚 Resources", category_counts.get("Resources", 0))
        with col4:
            st.metric("📦 Archives", category_counts.get("Archives", 0))

        # 신뢰도 통계
        st.subheader("📊 신뢰도 분포")
        confidences = [
            item["confidence"] for item in st.session_state.classification_history
        ]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0

        st.metric("평균 신뢰도", f"{avg_confidence:.0%}")

        # 차트 표시 (간단한 막대 그래프)
        st.bar_chart(category_counts)

    else:
        st.info("분류된 파일이 없습니다. TAB 1에서 파일을 업로드하세요.")

# 하단 정보
st.divider()
st.caption("FlowNote MVP v3.1 | LangChain + LangGraph 통합 | Made with ❤️ by Jay")
