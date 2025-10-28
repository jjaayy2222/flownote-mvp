# backend/balidators.py

"""
FileValidator 클래스 = 파일 검증 모듈 ≒ 파일 문지기
    - validate_file_size() = 파일 크기 검증 로직
    - validate_extension() = 파일 확장자 검증 로직
    - validate_file() = 전체 파일에 대한 종합 검증 로직

QueryValidator 클래스 = 검색 쿼리 검증 모듈 ≒ 검색어 경찰관
    - validate_query() = 검색어 길이 및 내용 검증

APIKeyValidator 클래스 = API 검증 모듈 ≒ 금고비밀번호 검사원
    - validate_api_keys() = 모든 필수 API 키 및 BASE URL에 대한 통합 검증
"""

import os
from typing import Tuple, Optional
from pathlib import Path


class ValidationError(Exception):
    """커스텀 검증 에러 클래스"""
    pass


class FileValidator:
    """파일 유효성 검증 클래스"""
    
    def __init__(
        self, 
        max_file_size_mb: int = 200,            # 최대 파일 크기 기본값 (MB)
        allowed_extensions: list = None         # 허용된 파일 확장자 목록
    ):
        """
        Args:
            max_file_size_mb: 최대 파일 크기 (MB) 설정
            allowed_extensions: 허용된 확장자 리스트 설정
        """
        self.max_file_size_mb = max_file_size_mb                            # 최대 파일 크기 저장
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024           # 바이트 단위로 변환
        self.allowed_extensions = allowed_extensions or ['.pdf', '.txt', '.md']     # 허용 확장자 초기화
    
    def validate_file_size(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        파일 크기 검증 로직
        
        Args:
            file_path: 파일 경로 문자열
            
        Returns:
            (유효성, 에러 메시지) 튜플 반환
        """
        try:
            file_size = os.path.getsize(file_path)                          # 파일 크기 획득
            
            # 빈 파일 검증 (크기 0 확인)
            if file_size == 0:
                return False, "❌ 빈 파일입니다."
            
            # 최대 크기 검증 (설정된 최대 바이트 초과 확인)
            if file_size > self.max_file_size_bytes:
                size_mb = file_size / (1024 * 1024)                         # MB 단위로 변환
                return False, f"❌ 파일 크기가 너무 큽니다. ({size_mb:.1f}MB > {self.max_file_size_mb}MB)"
            
            # 크기 유효성 통과
            return True, None 
            
        except Exception as e:
            return False, f"❌ 파일 크기 확인 중 오류: {str(e)}"                 # 오류 처리 및 반환
    
    def validate_extension(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        파일 확장자 검증 로직
        
        Args:
            file_path: 파일 경로 문자열
            
        Returns:
            (유효성, 에러 메시지) 튜플 반환
        """
        ext = Path(file_path).suffix.lower()                                # 파일 확장자 추출 및 소문자 변환
        
        if ext not in self.allowed_extensions:
            allowed = ", ".join(self.allowed_extensions)                    # 허용 형식 목록 생성
            # 확장자 불일치 처리
            return False, f"❌ 지원하지 않는 파일 형식입니다. ({ext})\n지원 형식: {allowed}" 
        
        # 확장자 유효성 통과
        return True, None 
    
    def validate_file(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        전체 파일에 대한 종합 검증 실행
        
        Args:
            file_path: 파일 경로 문자열
            
        Returns:
            (유효성, 에러 메시지) 튜플 반환
        """
        # 1. 파일 존재 확인
        if not os.path.exists(file_path):
            return False, f"❌ 파일이 존재하지 않습니다: {file_path}"               # 존재 여부 검증
        
        # 2. 확장자 검증 실행
        valid, error = self.validate_extension(file_path)
        if not valid:
            return False, error                                               # 검증 결과 반환
        
        # 3. 크기 검증 실행
        valid, error = self.validate_file_size(file_path)
        if not valid:
            return False, error                                               # 검증 결과 반환
        
        return True, None                                                     # 최종 유효성 통과


class QueryValidator:
    """검색 쿼리 유효성 검증 클래스"""
    
    def __init__(
        self,
        min_length: int = 2,                                                 # 최소 쿼리 길이 설정
        max_length: int = 500                                                # 최대 쿼리 길이 설정
    ):
        """
        Args:
            min_length: 최소 쿼리 길이
            max_length: 최대 쿼리 길이
        """
        self.min_length = min_length                                        # 최소 길이 저장
        self.max_length = max_length                                        # 최대 길이 저장
    
    def validate_query(self, query: str) -> Tuple[bool, Optional[str]]:
        """
        검색 쿼리 검증 로직
        
        Args:
            query: 검색 쿼리 문자열
            
        Returns:
            (유효성, 에러 메시지) 튜플 반환
        """
        # 1. None 또는 공백만 있는 문자열 검증
        if not query or not query.strip():
            return False, "⚠️ 검색어를 입력해주세요."                            # 빈 쿼리 처리
        
        # 2. 공백만 있는지 검증
        if query.isspace():
            return False, "⚠️ 검색어는 공백만으로 구성될 수 없습니다."               # 공백 문자열 처리
        
        # 3. 길이 검증
        # 앞뒤 공백 제거 후 실제 길이 계산
        query_length = len(query.strip()) 
        
        if query_length < self.min_length:
            return False, f"⚠️ 검색어가 너무 짧습니다. (최소 {self.min_length}자)"      # 최소 길이 미달
        
        if query_length > self.max_length:
            return False, f"⚠️ 검색어가 너무 깁니다. (최대 {self.max_length}자)"       # 최대 길이 초과
        
        # 최종 유효성 통과
        return True, None 


class APIKeyValidator:
    """API 키 유효성 검증 클래스 (mlapi.run 프록시 사용 기준)"""
    
    @staticmethod
    def validate_api_keys() -> Tuple[bool, Optional[str]]:
        """
        모든 필수 API 키 및 BASE URL에 대한 통합 검증
        
        Returns:
            (유효성, 에러 메시지) 튜플 반환
        """
        # config 파일에서 변수 직접 임포트 시도
        try:
            from backend.config import (
                EMBEDDING_API_KEY,
                EMBEDDING_BASE_URL,
                GPT4O_API_KEY,
                GPT4O_BASE_URL
            )
        except ImportError as e:
            # 임포트 실패 처리
            return False, f"❌ config 파일 임포트 실패: {str(e)}" 
        
        # 1. 임베딩 API 키 검증 (필수 항목)
        if not EMBEDDING_API_KEY:
            # 키 존재 여부 확인
            return False, "❌ EMBEDDING_API_KEY가 설정되지 않았습니다.\n.env 파일을 확인하세요." 
        
        if not EMBEDDING_BASE_URL:
            # BASE URL 존재 여부 확인
            return False, "❌ EMBEDDING_BASE_URL이 설정되지 않았습니다.\n.env 파일을 확인하세요." 
        
        # 2. API 키 형식 검증 (JWT 토큰 형식, 'eyJ'로 시작)
        if not EMBEDDING_API_KEY.startswith("eyJ"):
            # JWT 형식 확인
            return False, "❌ EMBEDDING_API_KEY 형식이 올바르지 않습니다.\nJWT 토큰이어야 합니다. (eyJ로 시작)" 
        
        # 3. API 키 최소 길이 검증 (충분한 길이 확인)
        if len(EMBEDDING_API_KEY) < 50:
            # 길이 검증
            return False, "❌ EMBEDDING_API_KEY가 너무 짧습니다.\n올바른 키인지 확인하세요." 
        
        # 4. BASE_URL 형식 검증 (http:// 또는 https:// 시작 확인)
        if not EMBEDDING_BASE_URL.startswith(("http://", "https://")):
            # URL 스키마 확인
            return False, "❌ EMBEDDING_BASE_URL이 올바른 URL 형식이 아닙니다.\nhttp:// 또는 https://로 시작해야 합니다." 
        
        # 5. mlapi.run 프록시 URL 검증 (/v1 접미사 필수 확인)
        if "mlapi.run" in EMBEDDING_BASE_URL and not EMBEDDING_BASE_URL.endswith("/v1"):
            # mlapi.run 프록시 경로 검증
            return False, "⚠️ EMBEDDING_BASE_URL이 /v1로 끝나지 않습니다.\nmlapi.run 프록시는 /v1이 필요합니다." 
        
        # 6. GPT4O API 검증 (선택사항, 키가 있으면 BASE URL과 형식 검증)
        if GPT4O_API_KEY:
            if not GPT4O_API_KEY.startswith("eyJ"):
                # GPT4O 키 JWT 형식 확인
                return False, "❌ GPT4O_API_KEY 형식이 올바르지 않습니다.\nJWT 토큰이어야 합니다." 
            
            if not GPT4O_BASE_URL:
                # GPT4O BASE URL 존재 확인
                return False, "❌ GPT4O_API_KEY는 있지만 GPT4O_BASE_URL이 없습니다." 
        
        # 모든 키 및 URL 최종 유효성 통과
        return True, None 
    
    @staticmethod
    def validate_embedding_api() -> Tuple[bool, Optional[str]]:
        """
        임베딩 API 전용 검증 (단순 버전)
        
        Returns:
            (유효성, 에러 메시지) 튜플 반환
        """
        # config 파일에서 임베딩 관련 변수 임포트 시도
        try:
            from backend.config import EMBEDDING_API_KEY, EMBEDDING_BASE_URL
        except ImportError as e:
            return False, f"❌ config 임포트 실패: {str(e)}"                # 임포트 실패 처리
        
        if not EMBEDDING_API_KEY:
            return False, "❌ 임베딩 API 키가 설정되지 않았습니다."              # 키 존재 여부 확인
        
        if not EMBEDDING_BASE_URL:
            return False, "❌ 임베딩 BASE URL이 설정되지 않았습니다."           # BASE URL 존재 여부 확인
        
        # 최종 유효성 통과
        return True, None 