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
import requests

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request
from pydantic import BaseModel
from typing import Dict, Optional, List, Any
from datetime import datetime, timezone

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
# 모델 임포트
from backend.models.classification import (
    ClassifyRequest,
    ClassifyResponse,
    ClassificationRequest,
    ClassificationResponse,
    MetadataClassifyRequest,
    HybridClassifyRequest,
    ParallelClassifyRequest
)


import logging

logger = logging.getLogger(__name__)


# ============ Router 초기화 ============
router = APIRouter()                    # API Router 추가


# ============ 싱글톤 인스턴스 ============
# 요청마다 재사용하지 않음
injector = get_context_injector()


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


        # 2. ClassificationMetadataExtender DB 저장
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
            

        # ========== 저장 로직 추가: classification_log.csv 직접 저장 (백업) ==========
        try:
            from pathlib import Path
            import csv
            
            # CSV 파일 경로 (flownote-mvp/data/classifications/)
            PROJECT_ROOT = Path(__file__).parent.parent.parent
            CSV_DIR = PROJECT_ROOT / "data" / "classifications"
            CSV_DIR.mkdir(parents=True, exist_ok=True)
            CSV_PATH = CSV_DIR / "classification_log.csv"
            
            # CSV 헤더 확인 후 추가
            file_exists = CSV_PATH.exists()
            
            with open(CSV_PATH, mode='a', newline='', encoding='utf-8') as f:
                fieldnames = ['timestamp', 'user_id', 'file_id', 'category', 'confidence', 'keyword_tags']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                
                if not file_exists:
                    writer.writeheader()
                
                writer.writerow({
                    'timestamp': datetime.now().isoformat(),
                    'user_id': request.user_id or "anonymous",
                    'file_id': request.file_id or "unknown",
                    'category': conflict_result.get('final_category', 'Resources') if 'conflict_result' in locals() else 'Resources',
                    'confidence': round(conflict_result.get('confidence', 0.0), 2) if 'conflict_result' in locals() else 0.0,
                    'keyword_tags': ','.join(new_keyword_tags if 'new_keyword_tags' in locals() else ['기타'])
                })
            
            logger.info(f"✅ CSV 직접 저장 완료: {CSV_PATH}")
            csv_direct_saved = True

        except Exception as csv_error:
            logger.warning(f"⚠️ CSV 직접 저장 실패: {csv_error}")
            csv_direct_saved = False
        # ========== CSV 직접 저장 끝 ==========


        # ========== 저장 로직 추가 2: data/log/ JSON 파일 저장 ==========
        try:
            from pathlib import Path
            import json
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            
            # JSON 로그 경로 (flownote-mvp/data/log/)
            PROJECT_ROOT = Path(__file__).parent.parent.parent
            LOG_DIR = PROJECT_ROOT / "data" / "log"
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            
            safe_snapshot_id = str(para_result.get('snapshot_id', 'snap_unknown')) if 'para_result' in locals() else 'snap_unknown'
            
            log_data = {
                "timestamp": timestamp,
                "user_id": request.user_id or "anonymous",
                "file_id": request.file_id or "unknown",
                "text_preview": request.text[:100],
                "category": conflict_result.get('final_category', 'Resources') if 'conflict_result' in locals() else 'Resources',
                "confidence": float(conflict_result.get('confidence', 0.0) if 'conflict_result' in locals() else 0.0),
                "keyword_tags": new_keyword_tags if 'new_keyword_tags' in locals() else ['기타'],
                "snapshot_id": safe_snapshot_id,
                "user_areas": request.areas,
                "matched_context": keyword_result.get('user_context_matched', False) if 'keyword_result' in locals() else False
            }
            
            json_filename = LOG_DIR / f"classification_{timestamp}.json"
            
            with open(json_filename, "w", encoding="utf-8") as f:
                json.dump(log_data, f, ensure_ascii=False, indent=2)
            
            
            logger.info(f"✅ JSON 로그 저장: {json_filename.name}")
            json_saved = True

        except Exception as json_error:
            logger.warning(f"⚠️ JSON 로그 저장 실패: {json_error}")
            json_saved = False
        # ========== JSON 저장 끝 ==========


        # ========== 저징 로직 추가_3 : user_context_mapping.json 누적 저장 ==========

        try:
            from pathlib import Path
            import json
            from datetime import datetime  # ✅ 반드시 필요
            
            # user_context_mapping.json 경로 (flownote-mvp/data/context/)
            PROJECT_ROOT = Path(__file__).parent.parent.parent
            CONTEXT_DIR = PROJECT_ROOT / "data" / "context"
            CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
            CONTEXT_PATH = CONTEXT_DIR / "user_context_mapping.json"
            
            # 기존 데이터 로드
            if CONTEXT_PATH.exists():
                with open(CONTEXT_PATH, "r", encoding="utf-8") as f:
                    context_data = json.load(f)
            else:
                context_data = {}
            
            # 수정: 사용자 컨텍스트 업데이트
            try:
                # ✅ FastAPI request에서 user_id 가져오기 (없으면 anonymous)
                user_id = getattr(request, "user_id", None) or "anonymous"
                
                # ✅ 기본 구조 먼저 보장
                if user_id not in context_data:
                    context_data[user_id] = {
                        "occupation": getattr(request, "occupation", None) or "일반 사용자",
                        "areas": getattr(request, "areas", None) or [],
                        "interests": getattr(request, "interests", None) or [],
                        "recent_categories": [],
                        "total_classifications": 0,
                        "last_updated": datetime.now().isoformat()
                    }
                
                # ✅ 각 필드 안전하게 업데이트
                if "recent_categories" not in context_data[user_id]:
                    context_data[user_id]["recent_categories"] = []
                if "total_classifications" not in context_data[user_id]:
                    context_data[user_id]["total_classifications"] = 0
                
                # 최근 카테고리 추가
                final_category = conflict_result.get('final_category', 'Resources') if conflict_result else 'Resources'
                context_data[user_id]["recent_categories"].append(final_category)
                context_data[user_id]["recent_categories"] = context_data[user_id]["recent_categories"][-10:]
                
                # 통계 업데이트
                context_data[user_id]["total_classifications"] += 1
                context_data[user_id]["last_updated"] = datetime.now().isoformat()
                
                # 저장
                with open(CONTEXT_PATH, "w", encoding="utf-8") as f:
                    json.dump(context_data, f, ensure_ascii=False, indent=2)
                logger.info(f"✅ user_context_mapping.json 저장: {user_id}")
                context_saved = True
            except Exception as context_error:
                logger.warning(f"⚠️ user_context_mapping.json 저장 실패: {context_error}")
                context_saved = False

        except Exception as context_error:
            logger.warning(f"⚠️ user_context_mapping.json 저장 실패: {context_error}")
            context_saved = False

        # ========== user_context_mapping.json 저장 끝 ==========


        # 4. log_info 생성
        log_info = {
            "csv_log": "data/classifications/classification_log.csv",
            "db_saved": saved_file_id is not None,
            "csv_direct_saved": csv_direct_saved if 'csv_direct_saved' in locals() else False,
            "json_log": json_filename.name if 'json_filename' in locals() and json_saved else None,
            "context_saved": context_saved if 'context_saved' in locals() else False,
            "log_directory": "data/log"
        }

        logger.info(f"✅ Step 5 완료 - CSV DataManager: {csv_saved}, CSV Direct: {csv_direct_saved if 'csv_direct_saved' in locals() else False}, JSON: {json_saved if 'json_saved' in locals() else False}, Context: {context_saved if 'context_saved' in locals() else False}")


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
            csv_log_result=csv_log_result if 'csv_log_result' in locals() else {},                      # CSV 로그 결과
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
# 파일 업로드 분류 엔드포인트 수정 (로그 추가)
# ============================================================
"""
backend/routes/classifier_routes.py
파일 업로드 기반 분류 전용 라우터
"""

@router.post("/file", response_model=ClassifyResponse)
async def classify_file(
    request: Request, 
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(None),
    file_id: Optional[str] = Form(None),
    occupation: Optional[str] = Form(None),
    areas: Optional[str] = Form(None),
    interests: Optional[str] = Form(None),
    selected_category: Optional[str] = Form(None)
):
    """파일 업로드 기반 분류 API - Form 데이터 + 중복 저장 로직 포함"""
    try:
        import json
        from pathlib import Path
        import csv
        import time

        # === 초기 상태값 보장 ===
        csv_saved = False
        csv_direct_saved = False
        json_saved = False
        context_saved = False
        csv_log_result = None
        json_filename = None
        areas_list = None
        
        # ============================================================
        # Step 1: 파일 읽기 + Form 데이터 파싱
        # ============================================================
        content = await file.read()
        text = content.decode("utf-8", errors="ignore") if isinstance(content, (bytes, bytearray)) else str(content)

        # JSON string을 list로 변환 (안전하게 처리)
        try:
            areas_list = json.loads(areas) if areas else []
        except Exception:
            areas_list = []
        try:
            interests_list = json.loads(interests) if interests else []
        except Exception:
            interests_list = []

        logger.info(f"📂 파일 읽기: {file.filename}")

        # ============================================================
        # Step 2: 사용자 컨텍스트 생성
        # ============================================================
        # 우선 Form으로 전달된 user_id를 우선 사용하고, 없으면 request.state에서 찾음
        effective_user_id = user_id or getattr(request.state, "user_id", None) or "anonymous"
        
        # ✅ DataManager에서 사용자 프로필 로드
        data_manager = DataManager()
        user_profile = data_manager.get_user_profile(effective_user_id)
        
        # 프로필이 있으면 사용, 없으면 Form 데이터 사용
        if user_profile:
            occupation_value = user_profile.get("occupation", "일반 사용자")
            # CSV에서 읽은 areas는 문자열이므로 리스트로 변환
            stored_areas = user_profile.get("areas", "")
            areas_list = [a.strip() for a in stored_areas.split(",")] if stored_areas else areas_list or []
            stored_interests = user_profile.get("interests", "")
            interests_list = [i.strip() for i in stored_interests.split(",")] if stored_interests else interests_list or []
            logger.info(f"✅ 프로필 로드 성공: {occupation_value}, areas={len(areas_list)}개")
        else:
            occupation_value = occupation or "일반 사용자"
            logger.warning(f"⚠️ 프로필 없음, Form 데이터 사용")

        user_context = {
            "user_id": effective_user_id,
            "file_id": file_id or file.filename,
            "occupation": occupation_value,
            "areas": areas_list,
            "interests": interests_list,
            "context_keywords": {
                area: [area, f"{area} 관련", f"{area} 업무", f"{area} 프로젝트"]
                for area in areas_list
            } if areas_list else {}
        }

        logger.info(f"🔍 사용자 컨텍스트 생성 시작...:")
        logger.info(f"   - Occupation: {user_context['occupation']}")
        logger.info(f"   - Areas: {user_context['areas']}")
        logger.info(f"   - Context Keywords: {list(user_context['context_keywords'].keys())}")
        
        logger.info(f"🔍 사용자 컨텍스트 생성 완료 (user_id={effective_user_id})")

        # ============================================================
        # Step 3: PARA 분류
        # ============================================================
        try:
            para_result = await run_para_agent(
                text=text,
                metadata={
                    "user_id": effective_user_id,
                    "file_id": file_id or file.filename,
                    "occupation": occupation,
                    "areas": areas_list,
                    "interests": interests_list
                    #"user_id": request.user_id,
                    #"file_id": request.file_id,
                    #"occupation": request.occupation,
                    #"areas": request.areas,
                    #"interests": request.interests          # 사용자 맥락 전달            
                }
            )
            logger.info(f"✅ PARA 분류 완료:")
            logger.info(f"   - Category: {para_result.get('category')}")
            logger.info(f"   - Confidence: {para_result.get('confidence')}")
            logger.info(f"   - Snapshot ID: {para_result.get('snapshot_id')}")
            
        except Exception as para_error:
            logger.error(f"❌ PARA 분류 실패: {para_error}", exc_info=True)
            para_result = {
                "category": "Resources",
                "confidence": 0.0,
                "snapshot_id": f"snap_failed_{int(datetime.now(timezone.utc).timestamp())}"
            }

        # ============================================================
        # Step 4: 키워드 추출
        # ============================================================

        keyword_classifier = KeywordClassifier()                # 매번 새 인스턴스!

        logger.info(f"🔍 키워드 분류 시작 (Instance ID: {keyword_classifier.instance_id})")

        # ✅ 수정: aclassify 호출 후 안전하게 tags 추출
        keyword_result = await keyword_classifier.aclassify(
            text=text,
            user_context=user_context
        )

        # ✅ 핵심 수정: tags 추출 로직 강화
        raw_tags = keyword_result.get('tags', [])
        logger.info(f"📦 Raw tags from LLM: {raw_tags} (type: {type(raw_tags)})")

        # 1. None이거나 빈 값 처리
        if not raw_tags:
            new_keyword_tags = ['기타']
            logger.warning(f"⚠️  Tags가 비어있음, 기본값 사용: {new_keyword_tags}")
            
        # 2. 문자열인 경우 (LLM이 리스트 대신 문자열로 반환한 경우)
        elif isinstance(raw_tags, str):
            # 쉼표로 구분된 문자열인지 확인
            if ',' in raw_tags:
                new_keyword_tags = [tag.strip() for tag in raw_tags.split(',') if tag.strip()]
            else:
                new_keyword_tags = [raw_tags.strip()] if raw_tags.strip() else ['기타']
            logger.info(f"✅ 문자열을 리스트로 변환: {new_keyword_tags}")

        # 3. 리스트인 경우 (정상)
        elif isinstance(raw_tags, list):
            # 빈 리스트 또는 모든 요소가 비어있는 경우
            valid_tags = [str(tag).strip() for tag in raw_tags if tag and str(tag).strip()]
            new_keyword_tags = valid_tags if valid_tags else ['기타']
            logger.info(f"✅ 리스트 검증 완료: {len(valid_tags)}개 태그")

        # 4. 그 외 예상치 못한 타입
        else:
            new_keyword_tags = ['기타']
            logger.warning(f"⚠️  예상치 못한 타입 {type(raw_tags)}, 기본값 사용")

        # ✅ 최종 검증: 최소 1개 이상의 태그 보장
        if not new_keyword_tags or len(new_keyword_tags) == 0:
            new_keyword_tags = ['기타']
            logger.warning(f"⚠️  최종 검증 실패, 강제 기본값 설정")

        logger.info(f"✅ 키워드 분류 완료:")
        logger.info(f"   - Instance ID: {keyword_result.get('instance_id')}")
        logger.info(f"   - Final Tags: {new_keyword_tags[:5]}")  # 상위 5개만 로그
        logger.info(f"   - Tags Count: {len(new_keyword_tags)}")
        logger.info(f"   - Confidence: {keyword_result.get('confidence')}")
        logger.info(f"   - User Context Matched: {keyword_result.get('user_context_matched')}")
        logger.info(f"   - Processing Time: {keyword_result.get('processing_time')}")

        # ============================================================
        # Step 5: 충돌 해결
        # ============================================================
        conflict_service = ConflictService()
        conflict_result = conflict_service.classify_text(
            para_result=para_result,
            keyword_result=keyword_result,
            text=text,
            user_context=user_context
        )

        logger.info(f"✅ 충돌 해결 완료: {conflict_result.get('final_category')}")

        # ============================================================
        # Step 6-1: DataManager CSV 로그 저장
        # ============================================================
        try:
            data_manager = DataManager()
            csv_log_result = data_manager.log_classification(
                user_id=effective_user_id,
                file_name=file_id or file.filename or "unknown",
                ai_prediction=conflict_result.get('final_category', 'Resources'),
                user_selected=selected_category,
                confidence=conflict_result.get('confidence', 0.0)
            )
            logger.info(f"✅ CSV DataManager 로그 저장 완료")
            csv_saved = True
        except Exception as csv_error:
            logger.warning(f"⚠️ CSV DataManager 로그 저장 실패: {csv_error}", exc_info=True)
            csv_saved = False
            csv_log_result = None

        # ============================================================
        # Step 6-2: CSV 직접 저장 (백업)
        # ============================================================
        try:
            PROJECT_ROOT = Path(__file__).parent.parent.parent
            CSV_DIR = PROJECT_ROOT / "data" / "classifications"
            CSV_DIR.mkdir(parents=True, exist_ok=True)
            CSV_PATH = CSV_DIR / "classification_log.csv"

            file_exists = CSV_PATH.exists()

            with open(CSV_PATH, mode='a', newline='', encoding='utf-8') as f:
                fieldnames = ['timestamp', 'user_id', 'file_id', 'category', 'confidence', 'keyword_tags']
                writer = csv.DictWriter(f, fieldnames=fieldnames)

                if not file_exists:
                    writer.writeheader()

                writer.writerow({
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'user_id': effective_user_id,
                    'file_id': file_id or file.filename,
                    'category': conflict_result.get('final_category', 'Resources'),
                    'confidence': round(conflict_result.get('confidence', 0.0), 2),
                    'keyword_tags': ','.join(new_keyword_tags)
                })

            logger.info(f"✅ CSV 직접 저장 완료: {CSV_PATH}")
            csv_direct_saved = True
        except Exception as csv_error:
            logger.warning(f"⚠️ CSV 직접 저장 실패: {csv_error}", exc_info=True)
            csv_direct_saved = False

        # ============================================================
        # Step 6-3: JSON 로그 저장
        # ============================================================
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
            LOG_DIR = PROJECT_ROOT / "data" / "log"
            LOG_DIR.mkdir(parents=True, exist_ok=True)

            log_data = {
                "timestamp": timestamp,
                "user_id": effective_user_id,
                "file_id": file_id or file.filename,
                "text_preview": text[:100],
                "category": conflict_result.get('final_category', 'Resources'),
                "confidence": float(conflict_result.get('confidence', 0.0)),
                "keyword_tags": new_keyword_tags,
                "snapshot_id": str(para_result.get('snapshot_id', 'snap_unknown')),
                "user_areas": areas_list,
                "matched_context": keyword_result.get('user_context_matched', False)
            }

            json_filename = LOG_DIR / f"classification_{timestamp}.json"
            with open(json_filename, "w", encoding="utf-8") as f:
                json.dump(log_data, f, ensure_ascii=False, indent=2)

            logger.info(f"✅ JSON 로그 저장: {json_filename.name}")
            json_saved = True
        except Exception as json_error:
            logger.warning(f"⚠️ JSON 로그 저장 실패: {json_error}", exc_info=True)
            json_saved = False
            json_filename = None

        # ============================================================
        # Step 6-4: user_context_mapping.json 저장 (안전하게)
        # ============================================================
        try:
            # user_context_mapping.json 경로 (flownote-mvp/data/context/)
            CONTEXT_DIR = PROJECT_ROOT / "data" / "context"
            CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
            CONTEXT_PATH = CONTEXT_DIR / "user_context_mapping.json"

            # 기존 데이터 로드
            if CONTEXT_PATH.exists():
                with open(CONTEXT_PATH, "r", encoding="utf-8") as f:
                    context_data = json.load(f)
            else:
                context_data = {}

            # 사용자 ID (이미 effective_user_id에 있음)
            uid = effective_user_id
            final_category = conflict_result.get('final_category', 'Resources') if conflict_result else 'Resources'

            # 기본 구조 보장
            context_data.setdefault(uid, {
                "occupation": occupation or "일반 사용자",
                "areas": areas_list or [],
                "interests": interests_list or [],
                "recent_categories": [],
                "total_classifications": 0,
                "last_updated": datetime.now(timezone.utc).isoformat()
            })

            # 안전 업데이트
            user_ctx = context_data[uid]
            user_ctx.setdefault("recent_categories", [])
            user_ctx.setdefault("total_classifications", 0)

            user_ctx["recent_categories"].append(final_category)
            # 중복 제거 + 최근 10개 유지
            user_ctx["recent_categories"] = list(dict.fromkeys(user_ctx["recent_categories"][-10:]))

            user_ctx["total_classifications"] += 1
            user_ctx["last_updated"] = datetime.now(timezone.utc).isoformat()

            # 안전하게 임시파일에 쓰고 교체
            temp_path = CONTEXT_PATH.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(context_data, f, ensure_ascii=False, indent=2)
            temp_path.replace(CONTEXT_PATH)

            logger.info(f"✅ user_context_mapping.json 저장: {uid}")
            context_saved = True
        except Exception as context_error:
            logger.warning(f"⚠️ user_context_mapping.json 저장 실패: {context_error}", exc_info=True)
            context_saved = False

        # ============================================================
        # Step 6-5: log_info 생성
        # ============================================================
        log_info = {
            "csv_log": str(CSV_PATH) if 'CSV_PATH' in locals() else "data/classifications/classification_log.csv",
            "db_saved": False,
            "csv_direct_saved": csv_direct_saved,
            "json_log": json_filename.name if json_filename and json_saved else None,
            "context_saved": context_saved,
            "log_directory": str(LOG_DIR) if 'LOG_DIR' in locals() else "data/log"
        }

        logger.info(
            f"✅ 전체 로그 저장 완료 - CSV DataManager: {csv_saved}, CSV Direct: {csv_direct_saved}, JSON: {json_saved}, Context: {context_saved}"
        )

        # ============================================================
        # Step 7: 응답 반환
        # ============================================================
        final_category = conflict_result.get('final_category', para_result.get('category', 'Resources'))

        response = ClassifyResponse(
            category=final_category,
            confidence=conflict_result.get('confidence', para_result.get('confidence', 0.0)),
            snapshot_id=str(para_result.get('snapshot_id', '')),
            conflict_detected=conflict_result.get('conflict_detected', False),
            requires_review=conflict_result.get('requires_review', False),
            keyword_tags=new_keyword_tags,
            reasoning=conflict_result.get('reason', ''),
            user_context_matched=keyword_result.get('user_context_matched', False),
            user_areas=areas_list,
            user_context=user_context,
            context_injected=len(areas_list) > 0,
            log_info=log_info,
            csv_log_result=csv_log_result
        )

        logger.info(f"✅ 전체 파일 분류 완료!")
        return response

    except Exception as e:
        logger.error(f"❌ 파일 분류 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"파일 분류 실패: {str(e)}")




