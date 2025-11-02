# backend/classifier/metadata_classifier.py

"""
메타데이터 기반 PARA 분류 전용 클래스
"""

import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class MetadataClassifier:
    """메타데이터를 사용한 PARA 분류기"""
    
    def __init__(self):
        """초기화"""
        self.classifier_dir = Path(__file__).parent
        logger.info("✅ MetadataClassifier initialized")
    
    def extract_metadata(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        딕셔너리에서 메타데이터 추출
        
        Args:
            data: 입력 데이터
            
        Returns:
            추출된 메타데이터
        """
        extracted = {
            "basic_info": data.get("basic_info", {}),
            "temporal_info": data.get("temporal_info", {}),
            "status_info": data.get("status_info", {}),
        }
        logger.info(f"메타데이터 추출 완료: {extracted.keys()}")
        return extracted
    
    def classify(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        메타데이터를 기반으로 PARA 분류
        
        Args:
            metadata: 메타데이터 딕셔너리
            
        Returns:
            분류 결과
        """
        from backend.classifier.langchain_integration import classify_with_metadata
        
        try:
            result = classify_with_metadata(metadata)
            logger.info(f"분류 완료: {result['category']}")
            return result
        except Exception as e:
            logger.error(f"분류 실패: {str(e)}")
            raise
    
    def batch_classify(self, metadata_list: list) -> list:
        """
        여러 메타데이터 배치 분류
        
        Args:
            metadata_list: 메타데이터 리스트
            
        Returns:
            분류 결과 리스트
        """
        results = []
        for i, metadata in enumerate(metadata_list):
            try:
                result = self.classify(metadata)
                results.append(result)
                logger.info(f"[{i+1}/{len(metadata_list)}] 분류 완료")
            except Exception as e:
                logger.error(f"[{i+1}] 분류 실패: {str(e)}")
                results.append({"status": "error", "message": str(e)})
        
        return results


# 편의 함수
def classify_metadata_simple(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """간단한 메타데이터 분류"""
    classifier = MetadataClassifier()
    return classifier.classify(metadata)


"""test_result



"""