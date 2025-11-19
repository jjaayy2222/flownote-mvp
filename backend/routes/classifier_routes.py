# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/routes/classifier_routes.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
통합 분류 라우터 (Phase 3.1)

이 파일은 모든 분류 관련 엔드포인트를 통합합니다:
- 핵심 분류 (classify, file)
- 메타데이터 관리 (save, metadata, saved)
- 고급 분류 (text, metadata, hybrid, parallel, para, keywords)
"""

import os
import json
import time
import csv
import requests
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Optional, List, Any

from fastapi import FastAPI
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request
from pydantic import BaseModel


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 통합 모델 Import
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from backend.models import (
    ClassifyRequest,
    ClassifyResponse,
    ClassificationRequest,
    ClassificationResponse,
    ClassifyBatchRequest,
    ClassifyBatchResponse,
    MetadataClassifyRequest,
    HybridClassifyRequest,
    ParallelClassifyRequest,
    FileMetadata,
    SaveClassificationRequest,
    SearchRequest,
    HealthCheckResponse,
    MetadataResponse,
    ErrorResponse,
    SuccessResponse,
)

from backend.models.conflict import (
    ConflictRecord,
    ConflictReport
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 분류 엔진 Import
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 함수 임포트
from backend.classifier.langchain_integration import (
    classify_with_langchain,
    classify_with_metadata,
    hybrid_classify
)
from backend.classifier.context_injector import get_context_injector
from backend.classifier.para_agent import run_para_agent
from backend.data_manager import save_json_log
save_func = save_json_log.__func__ if hasattr(save_json_log, "__func__") else save_json_log

# 클래스 임포트
from backend.services.conflict_service import conflict_service
from backend.data_manager import DataManager
from backend.classifier.keyword_classifier import KeywordClassifier
from backend.services.parallel_processor import ParallelClassifier
from backend.services.conflict_service import ConflictService
from backend.chunking import TextChunker
from backend.classifier.langchain_integration import PARAClassificationOutput
from backend.classifier.metadata_classifier import MetadataClassifier
from backend.classifier.para_classifier import PARAClassifier
from backend.classifier.context_injector import ContextInjector
from backend.database.metadata_schema import ClassificationMetadataExtender

import uuid
import logging

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API Router 추가
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
router = APIRouter()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 싱글톤 인스턴스
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

injector = get_context_injector() 

data_manager = DataManager()            # DataManager 인스턴스

chunker = TextChunker(chunk_size=500, chunk_overlap=50)

SAVED_CLASSIFICATIONS = {}              # In-memory storage



# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API 엔드포인트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📌 Section 1: Main API (2개)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Tag만 추가
@router.post("/classify", response_model=ClassifyResponse, tags=["Classification", "Main API", "Text"])
async def classify_text(request: ClassifyRequest):
    """
    메인 텍스트 분류 (KeywordClassifier + ConflictService)
    
    - 매번 새로운 KeywordClassifier 인스턴스 생성
    - 비동기 aclassify() 사용
    - 사용자 맥락(occupation, areas, interests) 완전 반영
    - 새 keyword_tags 매번 생성
    - DB 및 로그에 저장
    
    Example:
        POST /api/classifier/classify
        {
            "text": "프로젝트 완성하기",
            "user_id": "user_123",
            "occupation": "개발자",
            "areas": ["백엔드", "AI"],
            "interests": ["머신러닝"]
        }
    """
    try:
        logger.info(f"📝 분류 요청 시작:")
        logger.info(f"   - Text: {request.text[:50]}...")
        logger.info(f"   - User ID: {request.user_id}")
        logger.info(f"   - Occupation: {request.occupation}")
        logger.info(f"   - Areas: {request.areas}")
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
        # Step 2: PARA 분류
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
        # Step 3: 키워드 추출
        # ============================================================
        keyword_classifier = KeywordClassifier()
        
        logger.info(f"🔍 키워드 분류 시작 (Instance ID: {keyword_classifier.instance_id})")
        
        keyword_result = await keyword_classifier.aclassify(
            text=request.text,
            user_context=user_context
        )
        
        # 키워드 안전 처리
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
        
        conflict_result = await conflict_service.classify_text(
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
        # Step 5: 최종 카테고리 결정 + 로그 저장 + 응답 반환 (완벽 정리판)
        # ============================================================

        # 1. 최종 카테고리 결정 (이 줄이 제일 중요!)
        final_category = (
            conflict_result.get("final_category")
            or para_result.get("category")
            or "Resources"
        )

        # 2. DataManager로 CSV 로그 기록 (기존에 있던 거 재사용)
        csv_log_result = {}
        try:
            csv_log_result = data_manager.log_classification(
                user_id=request.user_id or "anonymous",
                file_name=request.file_id or "text_input",
                ai_prediction=final_category,
                user_selected=None,
                confidence=conflict_result.get("confidence", 0.0)
            )
        except Exception as e:
            logger.warning(f"DataManager CSV 기록 실패 (무시): {e}")

        # 3. 통합 로그 저장 (CSV + JSON + 사용자 컨텍스트)
        try:
            from pathlib import Path
            import json
            import csv
            from datetime import datetime as dt

            PROJECT_ROOT = Path(__file__).parent.parent.parent
            LOG_DIR = PROJECT_ROOT / "data" / "log"
            CSV_DIR = PROJECT_ROOT / "data" / "classifications"
            CTX_DIR = PROJECT_ROOT / "data" / "context"

            for d in (LOG_DIR, CSV_DIR, CTX_DIR):
                d.mkdir(parents=True, exist_ok=True)

            timestamp = dt.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]

            # 3-1. CSV 백업 저장
            csv_path = CSV_DIR / "classification_log.csv"
            file_exists = csv_path.exists()
            with open(csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["timestamp","user_id","file_id","category","confidence","keyword_tags"])
                if not file_exists:
                    writer.writeheader()
                writer.writerow({
                    "timestamp": dt.now().isoformat(),
                    "user_id": request.user_id or "anonymous",
                    "file_id": request.file_id or "text_input",
                    "category": final_category,
                    "confidence": round(conflict_result.get("confidence", 0.0), 3),
                    "keyword_tags": ",".join(new_keyword_tags)
                })

            # 3-2. JSON 로그 저장
            json_path = LOG_DIR / f"classification_{timestamp}.json"
            json_log_data = {
                "timestamp": timestamp,
                "user_id": request.user_id or "anonymous",
                "text_preview": request.text[:100],
                "final_category": final_category,
                "keyword_tags": new_keyword_tags,
                "confidence": conflict_result.get("confidence", 0.0),
                "snapshot_id": str(para_result.get("snapshot_id", "unknown")),
                "user_areas": request.areas or [],
                "context_matched": keyword_result.get("user_context_matched", False)
            }
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(json_log_data, f, ensure_ascii=False, indent=2)

            # 3-3. 사용자 컨텍스트 누적 저장
            ctx_path = CTX_DIR / "user_context_mapping.json"
            ctx_data = {}
            if ctx_path.exists():
                try:
                    with open(ctx_path, "r", encoding="utf-8") as f:
                        ctx_data = json.load(f)
                except:
                    ctx_data = {}

            uid = request.user_id or "anonymous"
            ctx_data.setdefault(uid, {"occupation": request.occupation or "일반 사용자", "areas": [], "interests": [], "recent_categories": [], "total_classifications": 0})
            ctx_data[uid]["recent_categories"].append(final_category)
            ctx_data[uid]["recent_categories"] = ctx_data[uid]["recent_categories"][-10:]
            ctx_data[uid]["total_classifications"] += 1
            ctx_data[uid]["last_updated"] = dt.now().isoformat()

            with open(ctx_path, "w", encoding="utf-8") as f:
                json.dump(ctx_data, f, ensure_ascii=False, indent=2)

            log_info = {
                "csv_log": str(csv_path),
                "json_log": json_path.name,
                "context_saved": True,
                "log_directory": str(LOG_DIR)
            }

        except Exception as e:
            logger.warning(f"로그 저장 실패 (무시 가능): {e}")
            log_info = {"error": str(e)}

        # 4. 최종 응답
        response = ClassifyResponse(
            category=final_category,
            confidence=conflict_result.get("confidence", para_result.get("confidence", 0.0)),
            snapshot_id=str(para_result.get("snapshot_id", "")),
            conflict_detected=conflict_result.get("conflict_detected", False),
            requires_review=conflict_result.get("requires_review", False),
            keyword_tags=new_keyword_tags,
            reasoning=conflict_result.get("reason", ""),
            user_context_matched=keyword_result.get("user_context_matched", False),
            user_areas=request.areas or [],
            user_context=user_context,
            context_injected=bool(request.areas),
            log_info=log_info,
            csv_log_result=csv_log_result
        )

        logger.info(f"✅ 전체 분류 완료 → {response.category} | 키워드 {len(response.keyword_tags)}개")
        logger.info(f"   - Final Category: {response.category}")
        logger.info(f"   - Keyword Tags: {response.keyword_tags[:3]}...")
        logger.info(f"   - User Context Matched: {response.user_context_matched}")
        logger.info(f"   - Total Time: ~{keyword_result.get('processing_time', 'N/A')}")

        return response

    except Exception as e:
        logger.error(f"❌ 분류 프로세스 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"분류 실패: {str(e)}")


# classify_file → classify_file_main
@router.post("/file", response_model=ClassifyResponse, tags=["Classification", "Main API", "File Upload"])
async def classify_file_main(
    request: Request,
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(None),
    file_id: Optional[str] = Form(None),
    occupation: Optional[str] = Form(None),
    areas: Optional[str] = Form(None),
    interests: Optional[str] = Form(None),
    selected_category: Optional[str] = Form(None)
):
    """
    메인 파일 분류 (classify_text 재사용)
    
    - 파일 업로드 후 텍스트 추출
    - classify_text와 동일한 로직 사용
    - Form 데이터로 사용자 컨텍스트 전달
    
    Example:
        POST /api/classifier/file
        Content-Type: multipart/form-data
        
        file: test.txt
        user_id: user_123
        occupation: 개발자
        areas: ["백엔드", "AI"]
    """
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
        conflict_result = await conflict_service.classify_text(
            para_result=para_result,
            keyword_result=keyword_result,
            text=text,
            user_context=user_context
        )

        logger.info(f"✅ 충돌 해결 완료: {conflict_result.get('final_category')}")


        # ============================================================
        # Step 6: 최종 카테고리 결정 + 로그 저장 + 응답 반환 (완벽 정리판)
        # ============================================================

        # 1. 최종 카테고리 결정 (이 줄이 제일 중요!)
        final_category = (
            conflict_result.get("final_category")
            or para_result.get("category")
            or "Resources"
        )

        # 2. DataManager로 CSV 로그 기록 (기존에 있던 거 재사용)
        csv_log_result = {}
        try:
            csv_log_result = data_manager.log_classification(
                user_id=request.user_id or "anonymous",
                file_name=request.file_id or "text_input",
                ai_prediction=final_category,
                user_selected=None,
                confidence=conflict_result.get("confidence", 0.0)
            )
        except Exception as e:
            logger.warning(f"DataManager CSV 기록 실패 (무시): {e}")

        # 3. 통합 로그 저장 (CSV + JSON + 사용자 컨텍스트)
        try:
            from pathlib import Path
            import json
            import csv
            from datetime import datetime as dt

            PROJECT_ROOT = Path(__file__).parent.parent.parent
            LOG_DIR = PROJECT_ROOT / "data" / "log"
            CSV_DIR = PROJECT_ROOT / "data" / "classifications"
            CTX_DIR = PROJECT_ROOT / "data" / "context"

            for d in (LOG_DIR, CSV_DIR, CTX_DIR):
                d.mkdir(parents=True, exist_ok=True)

            timestamp = dt.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]

            # 3-1. CSV 백업 저장
            csv_path = CSV_DIR / "classification_log.csv"
            file_exists = csv_path.exists()
            with open(csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["timestamp","user_id","file_id","category","confidence","keyword_tags"])
                if not file_exists:
                    writer.writeheader()
                writer.writerow({
                    "timestamp": dt.now().isoformat(),
                    "user_id": request.user_id or "anonymous",
                    "file_id": request.file_id or "text_input",
                    "category": final_category,
                    "confidence": round(conflict_result.get("confidence", 0.0), 3),
                    "keyword_tags": ",".join(new_keyword_tags)
                })

            # 3-2. JSON 로그 저장
            json_path = LOG_DIR / f"classification_{timestamp}.json"
            json_log_data = {
                "timestamp": timestamp,
                "user_id": request.user_id or "anonymous",
                "text_preview": request.text[:100],
                "final_category": final_category,
                "keyword_tags": new_keyword_tags,
                "confidence": conflict_result.get("confidence", 0.0),
                "snapshot_id": str(para_result.get("snapshot_id", "unknown")),
                "user_areas": request.areas or [],
                "context_matched": keyword_result.get("user_context_matched", False)
            }
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(json_log_data, f, ensure_ascii=False, indent=2)

            # 3-3. 사용자 컨텍스트 누적 저장
            ctx_path = CTX_DIR / "user_context_mapping.json"
            ctx_data = {}
            if ctx_path.exists():
                try:
                    with open(ctx_path, "r", encoding="utf-8") as f:
                        ctx_data = json.load(f)
                except:
                    ctx_data = {}

            uid = request.user_id or "anonymous"
            ctx_data.setdefault(uid, {"occupation": request.occupation or "일반 사용자", "areas": [], "interests": [], "recent_categories": [], "total_classifications": 0})
            ctx_data[uid]["recent_categories"].append(final_category)
            ctx_data[uid]["recent_categories"] = ctx_data[uid]["recent_categories"][-10:]
            ctx_data[uid]["total_classifications"] += 1
            ctx_data[uid]["last_updated"] = dt.now().isoformat()

            with open(ctx_path, "w", encoding="utf-8") as f:
                json.dump(ctx_data, f, ensure_ascii=False, indent=2)

            log_info = {
                "csv_log": str(csv_path),
                "json_log": json_path.name,
                "context_saved": True,
                "log_directory": str(LOG_DIR)
            }

        except Exception as e:
            logger.warning(f"로그 저장 실패 (무시 가능): {e}")
            log_info = {"error": str(e)}

        # 4. 최종 응답
        response = ClassifyResponse(
            category=final_category,
            confidence=conflict_result.get("confidence", para_result.get("confidence", 0.0)),
            snapshot_id=str(para_result.get("snapshot_id", "")),
            conflict_detected=conflict_result.get("conflict_detected", False),
            requires_review=conflict_result.get("requires_review", False),
            keyword_tags=new_keyword_tags,
            reasoning=conflict_result.get("reason", ""),
            user_context_matched=keyword_result.get("user_context_matched", False),
            user_areas=request.areas or [],
            user_context=user_context,
            context_injected=bool(request.areas),
            log_info=log_info,
            csv_log_result=csv_log_result
        )

        logger.info(f"✅ 전체 분류 완료 → {response.category} | 키워드 {len(response.keyword_tags)}개")
        logger.info(f"   - Final Category: {response.category}")
        logger.info(f"   - Keyword Tags: {response.keyword_tags[:3]}...")
        logger.info(f"   - User Context Matched: {response.user_context_matched}")
        logger.info(f"   - Total Time: ~{keyword_result.get('processing_time', 'N/A')}")

        return response

    except Exception as e:
        logger.error(f"❌ 분류 프로세스 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"분류 실패: {str(e)}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📦 Section 2: Advanced API (4개)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 고급 분류 (기존 api_routes.py의 분류 로직)

# classify_file → classify_file_advanced
# "/classied/file" → "/advanced/file"
@router.post("/advanced/file", tags=["Classification", "Advanced", "LangGraph"])
async def classify_file_advanced(file: UploadFile = File(...)):
    """고급 파일 분류 (LangGraph + 메타데이터 저장)"""
    try:
        # 1. 파일 읽기
        content = await file.read()
        text = content.decode('utf-8')
        filename = file.filename
        
        logger.info(f"🚀 분류 시작: {filename}")
        
        # 2. 청킹
        chunks = chunker.chunk_text(text)
        chunk_count = len(chunks)
        
        # 3. 파일 ID 생성 (UUID)
        file_id = f"file_{uuid.uuid4().hex[:8]}"
        
        # 4. 메타데이터 저장
        try:
            data_manager.add_file(
                file_name=filename,
                file_size=len(content),
                chunk_count=chunk_count,
                embedding_dim=1536,
                model="text-embedding-3-small"
            )
            logger.info(f"✅ 메타데이터 저장: {file_id}")
        except Exception as e:
            logger.warning(f"⚠️ 메타데이터 저장 실패 (무시): {e}")
        
        # 5. LangGraph 기반 고도화 분류
        metadata = {
            "filename": filename,
            "file_size": len(content),
            "chunk_count": chunk_count,
            "uploaded_at": datetime.now().isoformat()
        }
        
        # 처음 2000자만 분류 (비용 절감)
        sample_text = text[:2000]
        
        # 🔥 Sync 버전 호출!
        try:
            para_result = await run_para_agent(
                text=sample_text,
                metadata=metadata
            )
            logger.info(f"✅ 분류 완료: {para_result['category']}")
        except Exception as e:
            logger.error(f"❌ LangGraph 에러: {e}")
            # Fallback
            para_result = {
                "category": "Resources",
                "keyword_tags": sample_text.split()[:10],
                "confidence": 0.5,
                "conflict_detected": False
            }
        
        # 6. 응답 생성
        response = {
            "final_category": para_result.get('category', 'Resources'),
            "para_category": para_result.get('category', 'Resources'),
            "keyword_tags": para_result.get('keyword_tags', [])[:10],  # 상위 10개만
            "confidence": para_result.get('confidence', 0.5),
            "confidence_gap": para_result.get('confidence_gap', 0.0),
            "conflict_detected": para_result.get('conflict_detected', False),
            "resolution_method": para_result.get('resolution_method', 'auto'),
            "requires_review": para_result.get('requires_review', False),
            # 메타데이터 추가
            "metadata": {
                "file_id": file_id,
                "filename": filename,
                "chunk_count": chunk_count,
                "file_size_kb": round(len(content) / 1024, 2),
                "text_preview": sample_text[:100] + "..." if len(sample_text) > 100 else sample_text
            }
        }
        return response
        
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="파일 인코딩 오류. UTF-8 파일만 지원합니다.")

    except Exception as e:
        logger.error(f"❌ 분류 에러: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Tag만 추가
@router.post("/save-classification", response_model=SuccessResponse, tags=["Classification", "Storage", "Save"])
async def save_classification(request: SaveClassificationRequest):
    """분류 결과 저장"""
    try:
        # 1. 실제 저장 (경로 받음)
        saved_path = save_func(
            user_id="system",  # 또는 request.user_id 있으면 그걸 쓰세요
            file_name=request.file_id,
            category=request.classification.get("category", "Unknown"),
            confidence=request.classification.get("confidence", 0.0),
            snapshot_id="manual_save",
            conflict_detected=False,
            requires_review=False,
            keyword_tags=request.classification.get("keyword_tags", []),
            reasoning="사용자가 직접 저장한 분류 결과",
            user_context="",
            user_profile=None,
            context_injected=False
        )
        
        logger.info(f"💾 저장됨: {request.file_id} → {saved_path}")
        
        return {
            "status": "saved",
            "file_id": request.file_id,
            "saved_path": saved_path,                    # 보너스: 실제 저장 위치 알려줌
            "message": "분류 결과가 성공적으로 저장되었습니다."
        }
    except Exception as e:
        logger.error(f"저장 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Tag만 추가
@router.get("/saved-files", tags=["Classification", "Storage", "List"])
async def get_saved_files():
    """저장된 파일 목록"""
    return SAVED_CLASSIFICATIONS

# Tag만 추가
@router.get("/metadata/{file_id}", response_model=Dict, tags=["Classification", "Metadata", "Query"])
async def get_metadata(file_id: str):
    """파일 메타데이터 조회"""
    try:
        metadata = data_manager.get_file(file_id)
        if not metadata:
            raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
        return metadata
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔬 Section 3: Specialized Methods (6개)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 고급 분류 메서드 (기존 classifier_routes.py)

# classify_text_endpoint → classify_text_langchain
# Tag 추가
@router.post("/text", tags=["Classification", "Advanced", "LangChain Only"])
async def classify_text_langchain(request: ClassificationRequest):
    """
    순수 텍스트 분류 (LangChain 기반)
    
    - 개발자/테스트용
    - LangChain만 사용, 충돌 해결 없음
    """
    """텍스트 분류 (LangChain 기반)"""
    try:
        # 기존 로직 유지 (classify_with_langchain 등)
        # Step 1: 사용자 컨텍스트 가져오기
        user_areas = []
        if request.user_id:
            try:
                user_context = data_manager.get_user_context(request.user_id)
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
        
        return ClassifyResponse(
            category=result.get("category", "Resources"),
            confidence=result.get("confidence", 0.0),
            keyword_tags=result.get("tags", []),
            reasoning=result.get("reasoning", ""),
            snapshot_id="",  # 메타데이터 분류는 스냅샷 없음
            conflict_detected=False,
            requires_review=False,
            user_context_matched=result.get("context_injected", False),
            user_areas=result.get("user_areas", []),
            user_context={},  # 필요하면 채우기
            context_injected=result.get("context_injected", False),
            log_info={"source": "metadata"},
            csv_log_result={}
        )
    
    except Exception as e:
        logger.error(f"메타데이터 분류 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Tag만 추가
@router.post("/metadata", response_model=ClassifyResponse, tags=["Classification", "Advanced", "Metadata Based"])
async def classify_metadata_endpoint(request: MetadataClassifyRequest):
    """메타데이터 분류"""
    try:
        result = classify_with_metadata(request.metadata)
        
        if request.user_id:
            result = injector.inject_context_from_user_id(
                user_id=request.user_id,
                ai_result=result
            )
        
        return ClassifyResponse(
            category=result.get("category", "Resources"),
            confidence=result.get("confidence", 0.0),
            keyword_tags=result.get("tags", []),
            reasoning=result.get("reasoning", ""),
            snapshot_id="",             # 메타데이터 분류는 스냅샷 없음
            conflict_detected=False,
            requires_review=False,
            user_context_matched=result.get("context_injected", False),
            user_areas=result.get("user_areas", []),
            user_context={},            # 필요하면 채우기
            context_injected=result.get("context_injected", False),
            log_info={"source": "metadata"},
            csv_log_result={}
        )
    
    except Exception as e:
        logger.error(f"메타데이터 분류 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Tag만 추가
@router.post("/hybrid", response_model=ClassifyResponse, tags=["Classification", "Advanced", "Hybrid"])
async def hybrid_classify_endpoint(request: HybridClassifyRequest):
    """하이브리드 분류 (텍스트 + 메타데이터)"""
    try:
        result = hybrid_classify(request.text, request.metadata)
        
        if request.user_id:
            result = injector.inject_context_from_user_id(
                user_id=request.user_id,
                ai_result=result
            )
        
        return ClassifyResponse(
            category=result.get("category", "Resources"),
            confidence=result.get("confidence", 0.0),
            keyword_tags=result.get("tags", []),
            reasoning=result.get("reasoning", ""),
            snapshot_id="",  # 메타데이터 분류는 스냅샷 없음
            conflict_detected=False,
            requires_review=False,
            user_context_matched=result.get("context_injected", False),
            user_areas=result.get("user_areas", []),
            user_context={},  # 필요하면 채우기
            context_injected=result.get("context_injected", False),
            log_info={"source": "metadata"},
            csv_log_result={}
        )
    
    except Exception as e:
        logger.error(f"메타데이터 분류 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Tag만 추가
@router.post("/parallel", tags=["Classification", "Advanced", "Parallel"])
async def parallel_classify_endpoint(request: ParallelClassifyRequest):
    """텍스트 + 메타데이터 병렬 분류"""
    try:
        # 병렬 처리
        result = ParallelClassifier.classify_parallel(
            text=request.text,
            metadata=request.metadata or {}
        )
        
        return ClassifyResponse(
            category=result.get("category", "Resources"),
            confidence=result.get("confidence", 0.0),
            keyword_tags=result.get("keyword_tags", []),
            reasoning=result.get("reasoning", ""),
            snapshot_id=result.get("snapshot_id", ""),
            conflict_detected=result.get("conflict_detected", False),
            requires_review=result.get("requires_review", False),
            user_context_matched=result.get("user_context_matched", False),
            user_areas=result.get("user_areas", []),
            user_context=result.get("user_context", {}),
            context_injected=result.get("context_injected", False),
            log_info=result.get("log_info", {"source": "parallel"}),
            csv_log_result=result.get("csv_log_result", {})
        )
    
    except Exception as e:
        logger.error(f"병렬 분류 실패: {e}")
        import traceback
        traceback.print_exc()
        return ClassifyResponse(
            category="Resources",
            confidence=0.0,
            keyword_tags=[],
            reasoning="병렬 분류 중 오류 발생",
            log_info={"error": str(e)},
            csv_log_result={}
        )


# Tag만 추가
@router.post("/para", tags=["Classification", "Specialized", "PARA"])
async def classify_para(request: ClassificationRequest):
    """PARA 분류 엔드포인트
        - /classify/para 로 접근 가능
    """
    try:
        result = classify_with_langchain(request.text)
        
        # 사용자 컨텍스트 주입
        if request.user_id:
            result = injector.inject_context_from_user_id(
                user_id=request.user_id,
                ai_result=result
            )
        
        return ClassifyResponse(
            category=result.get("category", "Resources"),
            confidence=result.get("confidence", 0.0),
            keyword_tags=result.get("tags", []),
            reasoning=result.get("reasoning", ""),
            snapshot_id="",  # 메타데이터 분류는 스냅샷 없음
            conflict_detected=False,
            requires_review=False,
            user_context_matched=result.get("context_injected", False),
            user_areas=result.get("user_areas", []),
            user_context={},  # 필요하면 채우기
            context_injected=result.get("context_injected", False),
            log_info={"source": "metadata"},
            csv_log_result={}
        )
    
    except Exception as e:
        logger.error(f"메타데이터 분류 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Tag만 추가
@router.post("/keywords", tags=["Classification", "Specialized", "Keywords"])
async def classify_keywords(request: ClassificationRequest):
    """키워드 분류 엔드포인트
        - 접근: POST http://localhost:8000/classify/keywords
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
        
        return ClassifyResponse(
            category=result.get("category", "Resources"),
            confidence=result.get("confidence", 0.0),
            keyword_tags=result.get("tags", []),
            reasoning=result.get("reasoning", ""),
            snapshot_id="",  # 메타데이터 분류는 스냅샷 없음
            conflict_detected=False,
            requires_review=False,
            user_context_matched=result.get("context_injected", False),
            user_areas=result.get("user_areas", []),
            user_context={},  # 필요하면 채우기
            context_injected=result.get("context_injected", False),
            log_info={"source": "metadata"},
            csv_log_result={}
        )
    
    except Exception as e:
        logger.error(f"메타데이터 분류 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# Section 4: History (1개)
# ========================================

# Tag 추가
# "/classify/snapshots" → "snapshots" 
@router.get("/snapshots", tags=["Classification", "History", "Query"])
async def get_snapshots():
    """저장된 스냅샷 조회"""
    return {"snapshots": conflict_service.get_snapshots()}
