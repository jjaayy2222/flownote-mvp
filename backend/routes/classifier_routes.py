# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/routes/classifier_routes.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
분류 라우트
- LangChain 기반 분류
- 사용자 컨텍스트 반영s
- 병렬 처리 지원
"""
import os
from pathlib import Path
import json
import time

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Dict, Optional, List, Any
from datetime import datetime

# 함수 임포트
from backend.classifier.langchain_integration import (
    classify_with_langchain,
    classify_with_metadata,
    hybrid_classify
)
from backend.classifier.context_injector import get_context_injector
from backend.classifier.para_agent import run_para_agent


# 클래스 임포트
from backend.classifier.langchain_integration import PARAClassificationOutput
from backend.services.parallel_processor import ParallelClassifier
from backend.classifier.keyword_classifier import KeywordClassifier
from backend.classifier.metadata_classifier import MetadataClassifier
from backend.classifier.para_classifier import PARAClassifier
from backend.classifier.context_injector import ContextInjector
from backend.services.conflict_service import ConflictService
from backend.routes.conflict_routes import ClassifyRequest, ClassifyResponse
from backend.metadata import FileMetadata
from backend.classifier.keyword_classifier import KeywordClassifier
from backend.data_manager import DataManager
from backend.database.metadata_schema import ClassificationMetadataExtender


import logging

logger = logging.getLogger(__name__)


# ============ Router 초기화 ============
router = APIRouter()                    # API Router 추가


# ============ 싱글톤 인스턴스 ============
# 요청마다 재사용하지 않음
injector = get_context_injector()



# ============ 요청 스키마들 ============

class ClassificationRequest(BaseModel):
    """텍스트 분류 요청"""
    text: str                       # 분류할 텍스트
    filename: str = "unknown"       # 선택사항
    user_id: Optional[str] = None   # 맥락 주입용 / 사용자 컨텍스트용
    

class ClassificationResponse(BaseModel):
    """분류 응답"""
    category: str
    confidence: float
    status: str = "success"
    # <--- 나머지 필드들

# 수정: 새 프롬프트에 맞춘 ClassifyRequest (user_context 필드 추가!)
class ClassifyRequest(BaseModel):
    """텍스트 분류 요청 (새 프롬프트 버전)"""
    text: str                               # 필수: 분류할 텍스트
    # 기존 필드들
    user_id: Optional[str] = None
    file_id: Optional[str] = None
    # 새 필드들 (프롬프트 {occupation}, {areas}, {interests} 대응)
    occupation: Optional[str] = None        # 직업
    areas: Optional[List[str]] = []         # 책임 영역
    interests: Optional[List[str]] = []     # 관심사

class ClassifyResponse(BaseModel):
    """분류 응답 (새 프롬프트 버전)"""
    category: str                           # 최종 카테고리
    confidence: float                       # 신뢰도
    # 기존 필드들 
    snapshot_id: Optional[str] = None   
    conflict_detected: bool = False
    requires_review: bool = False
    user_profile: dict = {}
    context_injected: bool = False
    
    # 새 필드들 (keyword_classifier 출력 반영)
    keyword_tags: List[str]                 # 키워드 태그 (매번 새로 생성)
    reasoning: str                          # 분류 이유 (프롬프트 reasoning)
    
    # 사용자 맥락 관련 (프롬프트 반영)
    user_context: Dict[str, Any] = {}       # 전달된 user_context 
    user_context_matched: bool = False      # 맥락 매칭 여부
    user_areas: Optional[List[str]] = []    # 사용된 영역



class MetadataClassifyRequest(BaseModel):
    """메타데이터 분류 요청"""
    metadata: Dict
    user_id: Optional[str] = None


class HybridClassifyRequest(BaseModel): 
    """하이브리드 분류 요청"""
    text: str
    metadata: Dict
    user_id: Optional[str] = None


class ParallelClassifyRequest(BaseModel):
    """병렬 분류 요청 (텍스트 + 메타데이터)"""
    text: str
    metadata: Dict
    filename: str = "unknown"
    user_id: Optional[str] = None


# ============ API 엔드포인트 ============

@router.post("/text")
async def classify_text_endpoint(request: ClassificationRequest):
    """텍스트 분류 (LangChain 기반)"""
    try:
        # 기존 로직 유지 (classify_with_langchain 등)
        # Step 1: 사용자 컨텍스트 가져오기
        user_areas = []
        if request.user_id:
            try:
                user_context = injector.get_user_context(request.user_id)
                user_areas = user_context.get('areas', [])
                
                logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                logger.info(f"📄 새 분류 요청")
                logger.info(f"User ID: {request.user_id}")
                logger.info(f"User Areas: {user_areas}")
                logger.info(f"Text Preview: {request.text[:100]}...")
                logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            except Exception as e:
                logger.warning(f"⚠️ Context loading failed: {e}")
        
        # Step 2: AI 분석 (LangChain 사용)
        # ⚠️ 주의: classify_with_langchain은 매번 새로운 분석을 수행해야 함!
        result = classify_with_langchain(request.text)
        
        # Step 3: 사용자 컨텍스트 주입
        if request.user_id and user_areas:
            result = injector.inject_context_from_user_id(
                user_id=request.user_id,
                ai_result=result
            )
            result["context_injected"] = True
            result["user_areas"] = user_areas
        else:
            result["context_injected"] = False
            result["user_areas"] = []

        # Step 4: 디버깅 로그
        logger.info(f"✅ 분류 완료:")
        logger.info(f"  - Category: {result.get('category', 'N/A')}")
        logger.info(f"  - Tags: {result.get('tags', [])[:5]}")
        logger.info(f"  - Context Injected: {result.get('context_injected', False)}")
        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        return {
            "status": "success",
            "result": result
        }
    
    except Exception as e:
        logger.error(f"❌ 텍스트 분류 실패: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": str(e)
        }



@router.post("/metadata")
async def classify_metadata_endpoint(request: MetadataClassifyRequest):
    """메타데이터 분류"""
    try:
        result = classify_with_metadata(request.metadata)
        
        if request.user_id:
            result = injector.inject_context_from_user_id(
                user_id=request.user_id,
                ai_result=result
            )
        
        return {
            "status": "success",
            "result": result
        }
    
    except Exception as e:
        logger.error(f"❌ 메타데이터 분류 실패: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


@router.post("/hybrid")
async def hybrid_classify_endpoint(request: HybridClassifyRequest):
    """텍스트 + 메타데이터 하이브리드 분류"""
    try:
        result = hybrid_classify(request.text, request.metadata)
        
        if request.user_id:
            result = injector.inject_context_from_user_id(
                user_id=request.user_id,
                ai_result=result
            )
        
        return {
            "status": "success",
            "result": result
        }
    
    except Exception as e:
        logger.error(f"❌ 하이브리드 분류 실패: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


@router.post("/parallel")
async def parallel_classify_endpoint(request: ParallelClassifyRequest):
    """텍스트 + 메타데이터 병렬 분류"""
    try:
        # ⚠️ 주의: ParallelClassifier.classify_parallel은 정적 메서드!
        # → 매번 새로운 분석을 수행함
        result = ParallelClassifier.classify_parallel(
            request.text,
            request.metadata
        )
        
        if request.user_id:
            result = injector.inject_context_from_user_id(
                user_id=request.user_id,
                ai_result=result
            )
        
        return {
            "status": "success",
            "result": result
        }
    
    except Exception as e:
        logger.error(f"❌ 병렬 분류 실패: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


@router.post("/para")
async def classify_para(request: ClassificationRequest):
    """PARA 분류 엔드포인트
    
        - /api/classify/para 로 접근 가능
    """
    try:
        result = classify_with_langchain(request.text)
        
        # 사용자 컨텍스트 주입
        if request.user_id:
            result = injector.inject_context_from_user_id(
                user_id=request.user_id,
                ai_result=result
            )
        
        return {
            "category": result.get("category", "Resources"),
            "status": "success",
            "result": result
        }
    
    except Exception as e:
        logger.error(f"❌ PARA 분류 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/keywords")
async def classify_keywords(request: ClassificationRequest):
    """키워드 분류 엔드포인트
        - 접근: POST http://localhost:8000/api/classify/keywords
    """
    try:
        logger.info(f"🔍 키워드 분류 요청: {request.text[:50]}...")
        
        # ⚠️ 주의: classify_with_langchain은 매번 새로운 LLM 호출!
        result = classify_with_langchain(request.text)
        
        # 사용자 컨텍스트 주입
        if request.user_id:
            result = injector.inject_context_from_user_id(
                user_id=request.user_id,
                ai_result=result
            )
        
        return {
            "status": "success",
            "category": {
                "keywords": result.get("tags", []),
                "confidence": result.get("confidence", 0.8)
            },
            "result": result
        }
    
    except Exception as e:
        logger.error(f"❌ 키워드 분류 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# /classify 엔드포인트
# ============================================================

@router.post("/classify", response_model=ClassifyResponse)
async def classify_text(request: ClassifyRequest):
    """텍스트 분류 API
    
    - 매번 새로운 KeywordClassifier 인스턴스 생성
    - 비동기 aclassify() 사용
    - 사용자 맥락(occupation, areas, interests) 완전 반영
    - 새 keyword_tags 매번 생성
    - DB 및 로그에 저장
    """
    try:
        logger.info(f"🔍 분류 요청 시작:")
        logger.info(f"   - Text: {request.text[:50]}...")
        logger.info(f"   - User ID: {request.user_id}")
        logger.info(f"   - File ID: {request.file_id}")
        logger.info(f"   - Occupation: {request.occupation}")
        logger.info(f"   - Areas: {request.areas}")
        logger.info(f"   - Interests: {request.interests}")
        
        # ============================================================
        # Step 1: 사용자 컨텍스트 생성
        # ============================================================
        
        user_context = {
            "user_id": request.user_id,
            "file_id": request.file_id,
            "occupation": request.occupation or "일반 사용자",      # 직업
            "areas": request.areas,                              # 영역
            "interests": request.interests,                      # 관심사
            "context_keywords": {                                # 자동 생성
                area: [area, f"{area} 관련", f"{area} 업무", f"{area} 프로젝트"]
                for area in (request.areas or [])
            }
        }
        
        logger.info(f"✅ 사용자 컨텍스트 생성:")
        logger.info(f"   - Occupation: {user_context['occupation']}")
        logger.info(f"   - Areas: {user_context['areas']}")
        logger.info(f"   - Context Keywords: {list(user_context['context_keywords'].keys())}")

        # ============================================================
        # Step 2: PARA 분류 (매번 새로)
        # ============================================================
        try:
            # PARA Agent 실행
            para_result = await run_para_agent(
                text=request.text,
                metadata={
                    "user_id": request.user_id,
                    "file_id": request.file_id,
                    "occupation": request.occupation,
                    "areas": request.areas,
                    "interests": request.interests          # 사용자 맥락 전달
                }
            )
            logger.info(f"✅ PARA 분류 완료:")
            logger.info(f"   - Category: {para_result.get('category')}")
            logger.info(f"   - Confidence: {para_result.get('confidence')}")
            logger.info(f"   - Snapshot ID: {para_result.get('snapshot_id')}")
        
        except Exception as para_error:
            logger.error(f"❌ PARA 분류 실패: {para_error}", exc_info=True)
            # 기본값 설정
            para_result = {
                "category": "Resources",
                "confidence": 0.0,
                "snapshot_id": f"snap_failed_{int(datetime.now().timestamp())}"
            }
        
        # ============================================================
        # Step 3: 키워드 추출 (비동기 + 새 인스턴스)
        # ============================================================
        keyword_classifier = KeywordClassifier()                # 매번 새 인스턴스!
        
        logger.info(f"🔍 키워드 분류 시작 (Instance ID: {keyword_classifier.instance_id})")
        keyword_result = await keyword_classifier.aclassify(    # 비동기 aclassify!
            text=request.text,
            user_context=user_context
        )
        
        # keyword_tags 추출 및 보장
        new_keyword_tags = keyword_result.get('tags', ['기타'])
        if not isinstance(new_keyword_tags, list):
            new_keyword_tags = [str(new_keyword_tags)] if new_keyword_tags else ['기타']
        else:
            new_keyword_tags = [str(tag) for tag in new_keyword_tags if str(tag).strip()]
            if not new_keyword_tags:
                new_keyword_tags = ['기타']

        logger.info(f"✅ 키워드 분류 완료:")
        logger.info(f"   - Instance ID: {keyword_result.get('instance_id')}")
        logger.info(f"   - Tags: {new_keyword_tags[:5]}")
        logger.info(f"   - Confidence: {keyword_result.get('confidence')}")
        logger.info(f"   - User Context Matched: {keyword_result.get('user_context_matched')}")
        logger.info(f"   - Processing Time: {keyword_result.get('processing_time')}")

        # ============================================================
        # Step 4: 충돌 해결
        # ============================================================
        
        conflict_service = ConflictService()
        conflict_result = conflict_service.classify_text(
            para_result=para_result,
            keyword_result=keyword_result,
            text=request.text,
            user_context=user_context                                   # 사용자 맥락 전달
        )

        logger.info(f"✅ 충돌 해결 완료:")
        logger.info(f"   - Final Category: {conflict_result.get('final_category')}")
        logger.info(f"   - Keyword Tags: {conflict_result.get('keyword_tags', new_keyword_tags)}")
        logger.info(f"   - Conflict Detected: {conflict_result.get('conflict_detected')}")
        logger.info(f"   - Requires Review: {conflict_result.get('requires_review')}")


        # ============================================================
        # Step 5: 완전 수정된 DataManager + DB 저장
        # ============================================================

        # 1. DataManager CSV 로그 누적
        try:
            data_manager = DataManager()
            
            # test_4_classification_log()와 정확히 동일한 5개 매개변수만 사용
            csv_log_result = data_manager.log_classification(
                user_id=request.user_id or "anonymous",
                file_name=request.file_id or "unknown",
                ai_prediction=conflict_result.get('final_category') if 'conflict_result' in locals() else '기타',
                user_selected=None,
                confidence=conflict_result.get('confidence', 0.0) if 'conflict_result' in locals() else 0.0
                # keyword_tags, user_areas 제거 - test와 매개변수 일치시키기
            )
            
            logger.info(f"✅ CSV 로그 저장 완료: data/classifications/classification_log.csv")
            csv_saved = True

        except Exception as csv_error:
            logger.warning(f"⚠️ CSV 로그 저장 실패: {csv_error}")
            csv_saved = False

        # 2. ClassificationMetadataExtender DB 저장 (성공 확인됨!)
        try:
            from backend.database.metadata_schema import ClassificationMetadataExtender
            
            extender = ClassificationMetadataExtender()
            
            # 안전한 데이터만 DB에 저장 (Snapshot 객체 제거)
            db_result = {
                "category": conflict_result.get('final_category', para_result.get('category', 'Resources')) if 'conflict_result' in locals() else para_result.get('category', 'Resources'),
                "keyword_tags": new_keyword_tags if 'new_keyword_tags' in locals() else ['기타'],
                "confidence": conflict_result.get('confidence', 0.0) if 'conflict_result' in locals() else 0.0,
                "conflict_detected": conflict_result.get('conflict_detected', False) if 'conflict_result' in locals() else False,
                "requires_review": conflict_result.get('requires_review', False) if 'conflict_result' in locals() else False,
                "snapshot_id": str(para_result.get('snapshot_id', 'snap_unknown')) if 'para_result' in locals() else f"snap_{int(time.time())}",
                "reasoning": conflict_result.get('reason', '분류 완료') if 'conflict_result' in locals() else '분류 완료',
                "user_context": {
                    "user_id": request.user_id or "anonymous",
                    "occupation": request.occupation,
                    "areas": request.areas,
                    "interests": request.interests
                }
            }
            
            db_filename = f"{request.user_id or 'anonymous'}_{int(time.time())}"
            saved_file_id = extender.save_classification_result(
                result=db_result,
                filename=db_filename
            )
            
            logger.info(f"✅ DB 저장 완료: file_id={saved_file_id}")

        except Exception as db_error:
            logger.warning(f"⚠️ DB 저장 실패 (무시하고 계속): {db_error}")
            saved_file_id = None

        # 3. 간단한 JSON 로그 (모든 객체 안전 처리)
        try:
            from pathlib import Path
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            
            # 안전한 JSON 데이터만 사용
            safe_snapshot_id = str(para_result.get('snapshot_id', 'snap_unknown')) if 'para_result' in locals() else 'snap_unknown'
            
            simple_log = {
                "timestamp": timestamp,
                "user_id": request.user_id or "anonymous",
                "text_preview": request.text[:100],
                "category": conflict_result.get('final_category', 'Resources') if 'conflict_result' in locals() else 'Resources',
                "confidence": float(conflict_result.get('confidence', 0.0) if 'conflict_result' in locals() else 0.0),
                "keyword_tags": new_keyword_tags if 'new_keyword_tags' in locals() else ['기타'],
                "snapshot_id": safe_snapshot_id,
                "user_areas": request.areas,
                "matched_context": keyword_result.get('user_context_matched', False) if 'keyword_result' in locals() else False
            }
            
            PROJECT_ROOT = Path(__file__).parent.parent.parent
            LOG_DIR = PROJECT_ROOT / "data" / "log"
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            
            json_filename = LOG_DIR / f"classification_clean_{timestamp}.json"
            
            with open(json_filename, "w", encoding="utf-8") as f:
                json.dump(simple_log, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ JSON 로그 저장: {json_filename.name}")
            json_saved = True

        except Exception as json_error:
            logger.warning(f"⚠️ JSON 로그 저장 실패: {json_error}")
            json_saved = False

        # 4. log_info 생성 (색깔 문제 해결!)
        log_info = {
            "csv_log": "data/classifications/classification_log.csv",
            "db_saved": saved_file_id is not None,
            "json_log": json_filename.name if 'json_filename' in locals() and json_saved else None,
            "log_directory": "data/log"
        }

        logger.info(f"✅ Step 5 완료 - CSV: {csv_saved}, DB: {saved_file_id is not None}, JSON: {json_saved}")


        # ============================================================
        # Step 6: 응답 반환
        # ============================================================
        
        # 수정 (우선순위 조정)
        final_category = conflict_result.get('final_category', para_result.get('category', '기타'))
        category = final_category if final_category != 'None' else para_result.get('category', 'Resources')
        
        response = ClassifyResponse(
            category=category,
            confidence=conflict_result.get('confidence', para_result.get('confidence', 0.0)),
            snapshot_id=str(para_result.get('snapshot_id', '')),
            conflict_detected=conflict_result.get('conflict_detected', False),
            requires_review=conflict_result.get('requires_review', False),
            keyword_tags=new_keyword_tags,                      # 새로 생성된 키워드
            reasoning=conflict_result.get('reason', ''),
            
            # 사용자 맥락 관련 (새 필드들)
            user_context_matched=keyword_result.get('user_context_matched', False),
            user_areas=request.areas,                           # 요청된 영역
            user_context=user_context,                          # 전달된 전체 컨텍스트
            context_injected=len(request.areas) > 0,            # 맥락 주입 여부
            log_info=log_info,                                  # 로그 정보
            csv_log_result=csv_log_result,                      # CSV 로그 결과
        )

        logger.info(f"✅ 전체 분류 완료!")
        logger.info(f"   - Final Category: {response.category}")
        logger.info(f"   - Keyword Tags: {response.keyword_tags[:3]}...")
        logger.info(f"   - User Context Matched: {response.user_context_matched}")
        logger.info(f"   - Total Time: ~{keyword_result.get('processing_time', 'N/A')}")

        return response

    except Exception as e:
        logger.error(f"❌ 분류 프로세스 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"분류 실패: {str(e)}")

# ============================================================
# 추가: 파일 업로드 분류 엔드포인트 (비동기)
# ============================================================

@router.post("/file")
async def classify_file(file: UploadFile = File(...)):
    """
    파일 업로드 및 분류 (비동기 버전)
    """
    try:
        # 파일 내용 읽기
        content = await file.read()
        text = content.decode('utf-8') if isinstance(content, bytes) else str(content)
        
        # 기본 user_context (파일 업로드라 user_id 없으면 anonymous)
        user_context = {
            "user_id": None,
            "file_id": file.filename,
            "occupation": "일반 사용자",
            "areas": [],
            "interests": [],
            "context_keywords": {}
        }

        # 분류 실행
        keyword_classifier = KeywordClassifier()
        keyword_result = await keyword_classifier.aclassify(
            text=text,
            user_context=user_context
        )

        new_keyword_tags = keyword_result.get('tags', ['기타'])
        logger.info(f"✅ 파일 분류 완료: {file.filename}")
        logger.info(f"   - Tags: {new_keyword_tags}")

        return {
            "status": "success",
            "filename": file.filename,
            "keyword_tags": new_keyword_tags,
            "confidence": keyword_result.get('confidence', 0.0)
        }

    except Exception as e:
        logger.error(f"❌ 파일 분류 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"파일 분류 실패: {str(e)}")
