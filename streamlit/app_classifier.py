# app_simple.py (완전 개선 버전)

import os
import sys
from pathlib import Path

# 프로젝트 루트 경로 추가 (중요!!!)
project_root = Path(__file__).parent.parent 
sys.path.insert(0, str(project_root))

import streamlit as st
import pypdf

from backend.classifier.para_classifier import PARAClassifier

st.set_page_config(page_title="PARA Classifier", page_icon="🤖")

# 세션 상태
if "classifier" not in st.session_state:
    st.session_state.classifier = PARAClassifier()

if "classification_result" not in st.session_state:
    st.session_state.classification_result = None

if "current_file" not in st.session_state:
    st.session_state.current_file = None

if "uploaded_file_key" not in st.session_state:
    st.session_state.uploaded_file_key = 0

st.title("🤖 PARA 분류 테스트")

# 💙 파일 업로드 (key 추가로 리셋 가능!)
uploaded_file = st.file_uploader(
    "파일 업로드",
    type=["pdf", "txt", "md"],
    help="PDF, TXT, MD 파일을 업로드하세요",
    key=f"file_uploader_{st.session_state.uploaded_file_key}"
)

# 💙 Step 1: 분류하기
if uploaded_file and st.button("분류하기"):
    try:
        # 파일 확장자 확인
        file_ext = uploaded_file.name.split('.')[-1].lower()
        
        # 파일 타입별 읽기
        if file_ext == 'pdf':
            pdf_reader = pypdf.PdfReader(uploaded_file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        elif file_ext in ['txt', 'md']:
            text = uploaded_file.read().decode('utf-8')
        else:
            st.error("지원하지 않는 파일 형식입니다")
            st.stop()
        
        # AI 분류
        result = st.session_state.classifier.classify(
            filename=uploaded_file.name,
            content=text.strip()
        )
        
        # 세션에 저장
        st.session_state.classification_result = result
        st.session_state.current_file = uploaded_file
        
        st.success("✅ 분류 완료!")
        
    except Exception as e:
        st.error(f"에러: {str(e)}")

# 💙 Step 2: 결과 표시 + 저장/초기화 버튼
if st.session_state.classification_result:
    result = st.session_state.classification_result
    
    # 결과 표시
    st.markdown(f"""
    **카테고리:** `{result['category']}` ({result['category_name']})  
    **이유:** {result['reason']}  
    **제안 폴더:** `{result['suggested_folder']}`  
    **신뢰도:** {result['confidence']:.0%}
    """)
    
    st.progress(result['confidence'])
    
    # 💙 버튼 2개 (저장 / 초기화)
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("💾 분류된 폴더에 저장", type="primary"):
            try:
                # 폴더 생성
                folder_path = Path("uploaded_files") / result['category']
                folder_path.mkdir(parents=True, exist_ok=True)
                
                # 파일 저장
                file_path = folder_path / st.session_state.current_file.name
                
                # 파일 다시 읽어서 저장
                st.session_state.current_file.seek(0)
                with open(file_path, 'wb') as f:
                    f.write(st.session_state.current_file.read())
                
                st.success(f"✅ `{result['category']}` 폴더에 저장 완료!")
                st.info(f"📁 저장 위치: `{file_path}`")
                
            except Exception as e:
                st.error(f"저장 실패: {str(e)}")
    
    with col2:
        # 💙 초기화 버튼
        if st.button("🔄 초기화", type="secondary"):
            # 세션 상태 초기화
            st.session_state.classification_result = None
            st.session_state.current_file = None
            
            # 파일 업로더도 리셋
            st.session_state.uploaded_file_key += 1
            
            # 페이지 리로드
            st.rerun()


st.divider()
st.caption("FlowNote MVP v3.2_simple | Made with ❤️ by Jay")