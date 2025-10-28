# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# app.py (파일 업로드 에러 핸들링 추가)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
FlowNote MVP - Streamlit UI
"""

# ━━━━━━━━━━━━━━━━━━━━
# 임포트
# ━━━━━━━━━━━━━━━━━━━━
import streamlit as st
import os
from datetime import datetime
import numpy as np
from collections import defaultdict                                                     # ✨ 추가!

# backend 클래스 임포트
from backend.embedding import EmbeddingGenerator
from backend.chunking import TextChunker
from backend.faiss_search import FAISSRetriever
from backend.metadata import FileMetadata
from backend.search_history import SearchHistory

# 검증 및 파일 처리 유틸리티 임포트
from backend.validators import FileValidator, QueryValidator, APIKeyValidator           # 유효성 검증 클래스
from backend.exceptions import FileValidationError, QueryValidationError, APIKeyError   # 예외 처리 클래스
from backend.utils import read_file_content, format_file_size                           # 파일 읽기 및 크기 포맷 함수

# ━━━━━━━━━━━━━━━━━━━━
# 페이지 설정
# ━━━━━━━━━━━━━━━━━━━━
st.set_page_config(
    page_title="FlowNote",                      # 브라우저 탭 제목
    page_icon="📚",                             # 브라우저 탭 아이콘
    layout="wide",                              # 넓은 레이아웃 사용 설정
    initial_sidebar_state="expanded"            # 사이드바 초기 확장 상태
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 세션 상태 초기화
# st.session_state는 웹사이트를 이용하는 동안 데이터를 저장하는 공간
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 업로드된 파일 경로 저장 목록
if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = []

# 청크된 문서 객체 저장 목록
if "documents" not in st.session_state:
    st.session_state.documents = []

# FAISS 검색 객체 (인덱스)
if "faiss_retriever" not in st.session_state:
    st.session_state.faiss_retriever = None

# 파일 메타데이터 관리 객체
if "file_metadata_manager" not in st.session_state:
    st.session_state.file_metadata_manager = FileMetadata()

# 검색 히스토리 관리 객체
if "search_history_manager" not in st.session_state:
    st.session_state.search_history_manager = SearchHistory()

# 청커 초기화
chunker = TextChunker(chunk_size=500, chunk_overlap=50)

# 임베딩 생성기 초기화
embedding_generator = EmbeddingGenerator()

# 검증기 초기화
file_validator = FileValidator(
    max_file_size_mb=200,                           # 최대 파일 크기 (200MB)
    allowed_extensions=['.pdf', '.txt', '.md']      # 허용되는 파일 확장자 목록 (PDF 추가)
)

query_validator = QueryValidator(
    min_length=2,           # 최소 검색어 길이
    max_length=500          # 최대 검색어 길이
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# API 키 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━
try:
    # API 키 유효성 검사
    valid, error = APIKeyValidator.validate_api_keys()  # 키 검증 함수 호출
    if not valid:
        st.error(f"🚨 {error}")  # 오류 메시지 표시
        st.info("💡 `.env` 파일에서 API 키를 확인하세요.")  # 안내 메시지 표시
        st.stop()  # 애플리케이션 실행 중지
except Exception as e:
    st.error(f"❌ API 키 검증 중 오류: {str(e)}")  # 예상치 못한 오류 처리
    st.stop()

# Document 클래스 정의
class SimpleDocument:
    """간단한 문서 클래스"""
    def __init__(self, page_content: str, metadata: dict = None):
        self.page_content = page_content
        self.metadata = metadata or {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 타이틀
# ━━━━━━━━━━━━━━━━━━━━━━━━━━
st.title("📚 FlowNote MVP")         # 메인 제목
st.markdown("AI 기반 문서 검색 시스템")  # 보조 설명

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 사이드바 (파일 업로드 및 처리)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━
with st.sidebar:
    st.header("⚙️ 설정")  # 설정 섹션 제목
    
    # 파일 업로드 위젯
    uploaded_files = st.file_uploader(
        "📁 문서 업로드",                                  # 파일 업로드 위젯 라벨
        type=["pdf", "txt", "md"],                      # 허용 파일 형식 (PDF, TXT, MD)
        accept_multiple_files=True,                     # 여러 파일 동시 업로드 허용
        help=f"지원 형식: PDF, TXT, MD\n최대 크기: {file_validator.max_file_size_mb}MB"
    )
    
    if uploaded_files:
        if st.button("📤 파일 처리하기", type="primary"):              # 파일 처리 시작 버튼
            with st.spinner("파일을 처리하는 중입니다..."):               # 작업 중 로딩 메시지
                try:
                    # 임시 저장 폴더 생성
                    os.makedirs("uploaded_files", exist_ok=True)    # 파일 저장 디렉토리 생성
                    saved_files = []                                # 저장 성공 파일 경로 목록
                    failed_files = []                               # 처리 실패 파일 이름 목록
                    
                    # 파일 저장 및 검증
                    for uploaded_file in uploaded_files:
                        # 파일 저장 경로 설정
                        file_path = os.path.join("uploaded_files", uploaded_file.name)
                        
                        try:
                            # 파일 임시 저장
                            with open(file_path, "wb") as f:
                                f.write(uploaded_file.getbuffer())                  # 업로드된 파일의 내용 쓰기
                            
                            # 파일 유효성 검사
                            valid, error = file_validator.validate_file(file_path)  # 유효성 검증 수행
                            if not valid:
                                st.warning(f"⚠️ {uploaded_file.name}: {error}")     # 경고 메시지 표시
                                os.remove(file_path)                                # 검증 실패 파일 삭제
                                failed_files.append(uploaded_file.name)             # 실패 목록에 추가
                                continue
                            
                            saved_files.append(file_path)                       # 성공 목록에 추가
                            st.success(f"✅ {uploaded_file.name} 검증 완료")      # 성공 메시지 표시
                            
                        except Exception as e:
                            st.error(f"❌ {uploaded_file.name}: {str(e)}")      # 파일 처리 오류 메시지
                            failed_files.append(uploaded_file.name)
                            if os.path.exists(file_path):
                                os.remove(file_path)                            # 오류 발생 시 임시 파일 삭제
                    
                    if not saved_files:
                        st.error("❌ 처리할 수 있는 파일이 없습니다.")                 # 처리 가능 파일이 없는 경우 오류
                        raise FileValidationError("모든 파일 검증 실패")
                    
                    # 파일 내용 읽기 및 청크 분할
                    all_documents = []                                          # 전체 문서 청크 저장 목록
                    
                    for file_path in saved_files:
                        try:
                            file_name = os.path.basename(file_path)             # 파일 이름 추출
                            file_size = os.path.getsize(file_path)              # 파일 크기 가져오기
                            
                            # 처리 상태 정보 표시
                            st.info(f"📄 {file_name} 처리 중... ({format_file_size(file_size)})")
                            
                            # ✨ 파일 읽기 (PDF/TXT/MD 자동 처리)
                            # 유틸리티 함수 사용 → 파일 내용 읽기
                            content = read_file_content(file_path)  
                            
                            if not content or not content.strip():
                                st.warning(f"⚠️ {file_name}: 파일이 비어있습니다.")   # 내용이 없는 경우 경고
                                continue
                            
                            # 텍스트 청크 분할
                            chunker = TextChunker()                              # 청크 분할 객체 생성
                            chunks = chunker.chunk_text(content)                 # 텍스트를 청크로 분할
                            
                            # Document 객체 생성 및 메타데이터 추가
                            for i, chunk in enumerate(chunks):
                                doc = {
                                    "content": chunk,  # 청크 내용
                                    "metadata": {
                                        "source": file_name,                     # 출처 파일 이름
                                        "chunk_index": i,                        # 청크 인덱스 번호
                                        "file_path": file_path,                  # 원본 파일 경로
                                        "file_size": file_size,                  # 원본 파일 크기
                                        "timestamp": datetime.now().isoformat()  # 처리 완료 시간
                                    }
                                }
                                # 전체 목록에 추가
                                all_documents.append(doc)
                            
                            # 청크 생성 완료 메시지
                            st.success(f"✅ {file_name}: {len(chunks)}개 청크 생성")
                            
                        except Exception as e:
                            # 파일 처리 중 오류 발생
                            st.error(f"❌ {os.path.basename(file_path)} 처리 실패: {str(e)}")
                            continue
                    
                    if not all_documents:
                        st.error("❌ 문서를 처리할 수 없습니다.")                  # 청크가 하나도 없는 경우
                        raise ValueError("문서 처리 실패")
                    
                    # 임베딩 생성
                    st.info(f"🔄 {len(all_documents)}개 청크 임베딩 생성 중...")  # 임베딩 생성 시작 메시지
                    
                    embedding_generator = EmbeddingGenerator()               # 임베딩 생성 객체
                    texts = [doc["content"] for doc in all_documents]        # 모든 청크 내용만 추출
                    
                    # ✨ dict에서 임베딩 추출!
                    result = embedding_generator.generate_embeddings(texts)
                    embeddings = result["embeddings"]
                    
                    st.info(f"✅ 임베딩 생성 완료 (토큰: {result['tokens']}, 비용: ${result['cost']:.6f})")
                    
                    # NumPy 배열로 변환
                    embeddings_np = np.array(embeddings, dtype=np.float32)
                    
                    # FAISS 인덱스 생성
                    retriever = FAISSRetriever(dimension=len(embeddings[0]))
                    retriever.add_documents(embeddings_np, all_documents)
                    
                    # 세션 상태 업데이트 (검색에 사용될 데이터 저장)
                    st.session_state.faiss_retriever = retriever            # FAISS 객체 저장
                    st.session_state.documents = all_documents              # 전체 문서 목록 저장
                    st.session_state.uploaded_files = saved_files           # 업로드 파일 경로 저장
                    
                    # ✨ 메타데이터 저장 (수정!)
                    # 파일별로 청크 개수 계산
                    file_chunk_counts = defaultdict(int)
                    file_info_map = {}                                      # 파일 정보 저장
                    
                    for doc in all_documents:
                        source = doc["metadata"]["source"]
                        file_chunk_counts[source] += 1
                        
                        # 파일 정보 저장 (첫 번째 청크에서)
                        if source not in file_info_map:
                            file_info_map[source] = {
                                "file_size": doc["metadata"]["file_size"]
                            }
                    
                    # 파일별로 한 번만 메타데이터 저장
                    for source, chunk_count in file_chunk_counts.items():
                        st.session_state.file_metadata_manager.add_file(
                            file_name=source,
                            file_size=file_info_map[source]["file_size"],
                            chunk_count=chunk_count,
                            embedding_dim=len(embeddings[0]),
                            model="text-embedding-3-small"
                        )
                    
                    st.success(f"🎉 총 {len(all_documents)}개 청크 처리 완료!")
                    st.info(f"📊 파일 {len(file_chunk_counts)}개 메타데이터 저장 완료")
                    
                    if failed_files:
                        st.warning(f"⚠️ 실패한 파일: {', '.join(failed_files)}")
                    
                except FileValidationError as e:
                    # 파일 검증 관련 오류
                    st.error(f"❌ 파일 검증 오류: {str(e)}")
                except Exception as e:
                    st.error(f"❌ 오류가 발생했습니다: {str(e)}")
                    import traceback
                    st.code(traceback.format_exc())
    
    # 현재 업로드된 파일 목록 표시
    if st.session_state.uploaded_files:
        st.markdown("---")
        st.subheader("📂 업로드된 파일")
        
        for file_path in st.session_state.uploaded_files:
            file_name = os.path.basename(file_path)                 # 파일 이름
            file_size = os.path.getsize(file_path)                  # 파일 크기
            st.text(f"📄 {file_name}")
            st.caption(f"   크기: {format_file_size(file_size)}")    # 읽기 쉬운 크기 포맷
            
        # 통계 추가
        st.markdown("---")
        st.subheader("📊 통계")

        # 메트릭 카드 (2열)
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric(
                label="파일 수",
                value=len(st.session_state.uploaded_files),
                help="업로드된 파일 개수"
            )
        
        with col2:
            st.metric(
                label="청크 수",
                value=len(st.session_state.documents) if st.session_state.documents else 0,
                help="생성된 텍스트 청크 개수"
            )
        
        # 검색 통계
        if st.session_state.search_history_manager.history:
            total_searches = len(st.session_state.search_history_manager.history)
            st.metric(
                label="검색 횟수",
                value=total_searches,
                help="총 검색 횟수"
            )




# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 컨텐츠 - 검색
# ━━━━━━━━━━━━━━━━━━━━━━━━━━
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
        # ✨ 쿼리 검증
        valid, error = query_validator.validate_query(query)
        
        if not valid:
            st.warning(f"⚠️ {error}")
        else:
            with st.spinner("검색 중입니다..."):
                try:
                    # FAISS 검색
                    search_results = st.session_state.faiss_retriever.search(query, k=k)
                    
                    # 검색 히스토리 저장
                    st.session_state.search_history_manager.add_search(
                        query=query,
                        results_count=len(search_results)
                    )
                    
                    # 결과 표시
                    st.success(f"✅ {len(search_results)}개 결과를 찾았습니다.")
                    
                    for i, result in enumerate(search_results, 1):
                        with st.expander(f"📄 결과 {i} - {result['metadata']['source']} (유사도: {result['score']:.2%})"):
                            st.markdown(f"**내용:**\n{result['content']}")
                            st.caption(f"출처: {result['metadata']['source']} (청크 {result['metadata']['chunk_index']})")
                    
                except Exception as e:
                    st.error(f"❌ 검색 중 오류가 발생했습니다: {str(e)}")
                    import traceback
                    st.code(traceback.format_exc())

    # 검색 섹션 아래에 히스토리 표시
    if st.session_state.faiss_retriever is not None:
        st.markdown("---")
        st.subheader("📜 최근 검색 기록")
        
        # 최근 10개 검색 기록 가져오기
        recent_searches = st.session_state.search_history_manager.get_recent_searches(limit=10)
        
        if recent_searches:
            # 테이블 형태로 표시
            st.markdown("**최근 10개 검색**")
            
            for search in recent_searches:
                # 검색 카드
                with st.container():
                    col1, col2, col3 = st.columns([3, 1, 2])
                    
                    with col1:
                        st.text(f"🔍 {search['query']}")
                    
                    with col2:
                        st.text(f"결과: {search['results_count']}개")
                    
                    with col3:
                        # 시간 포맷팅
                        from datetime import datetime
                        timestamp = datetime.fromisoformat(search['created_at'])
                        st.caption(timestamp.strftime("%m/%d %H:%M"))
                    
                    st.markdown("---")
        else:
            st.info("아직 검색 기록이 없습니다.")

else:
    st.info(
        """👋 **FlowNote에 오신 것을 환영합니다!** 👋 
        
        시작하려면:
        
            1. 왼쪽 사이드바에서 PDF,TXT, MD 파일을 업로드하세요
            2. "파일 처리하기" 버튼을 클릭하세요
            3. 검색어를 입력하여 문서를 검색하세요
            
        💡 Tip! - 여러 파일을 한 번에 업로드할 수 있습니다!
        """
        )


# ━━━━━━━━━━━━━━━━━━━━━━
# 푸터
# ━━━━━━━━━━━━━━━━━━━━━━
st.divider()
st.caption("FlowNote MVP v2.0 | Made with ❤️ by Jay")
