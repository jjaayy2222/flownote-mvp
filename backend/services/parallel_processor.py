# backend/services/parallel_processor.py

"""
병렬 분류 처리기
ThreadPoolExecutor를 사용해 텍스트 + 메타데이터 동시 분류
"""

import logging
import time
from typing import Dict
from concurrent.futures import ThreadPoolExecutor
from backend.classifier.langchain_integration import (
    classify_with_langchain,
    classify_with_metadata
    # hybrid_classify 
)

# 로깅 추가 
logger = logging.getLogger(__name__)


class ParallelClassifier:
    """병렬 분류 처리기"""
    
    @staticmethod
    def classify_parallel(text: str, metadata: Dict) -> Dict:
        """
        텍스트 + 메타데이터 병렬 분류
        
        Args:
            text: 분류할 텍스트
            metadata: 메타데이터 딕셔너리
            
        Returns:
            분류 결과 (text_result, metadata_result, execution_time)
        """
        start_time = time.time()
        
        # 에러 처리 추가 
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                # 두 개 작업을 동시에 실행
                text_future = executor.submit(classify_with_langchain, text)
                meta_future = executor.submit(classify_with_metadata, metadata)
                
                # 결과 수집
                text_result = text_future.result()
                meta_result = meta_future.result()
                
                # 성능 모니터링
                execution_time = time.time() - start_time
                
                # 로깅 추가
                logger.info(f"✅ 병렬 분류 완료 ({execution_time:.2f}초)")
                
                return {
                    "status": "success",
                    "text_result": text_result,
                    "metadata_result": meta_result,
                    "execution_time": round(execution_time, 2),
                    "strategy": "parallel"
                }
                
        except Exception as e:
            logger.error(f"❌ 병렬 분류 실패: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }


"""test_result



"""