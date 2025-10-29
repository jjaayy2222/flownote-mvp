# test_para_classifier.py

import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.classifier.para_classifier import PARAClassifier

def test_classifier():
    """간단한 테스트"""
    
    classifier = PARAClassifier()
    
    # 테스트 파일들
    test_files = [
        {
            "filename": "프로젝트_제안서.pdf",
            "content": "2025년 신규 프로젝트 제안서. 마감: 11월 15일"
        },
        {
            "filename": "Python_학습노트.md",
            "content": "파이썬 문법 정리. 지속적으로 업데이트 중."
        },
        {
            "filename": "AI_논문_모음.pdf",
            "content": "참고용 AI 관련 논문 모음집"
        },
        {
            "filename": "2024_완료_프로젝트.pdf",
            "content": "2024년에 완료된 프로젝트 최종 보고서"
        }
    ]
    
    print("=" * 50)
    print("PARA 분류 테스트")
    print("=" * 50)
    
    for test_file in test_files:
        result = classifier.classify(
            test_file["filename"],
            test_file["content"]
        )
        
        print(f"\n📄 {test_file['filename']}")
        print(f"    카테고리: {result['category']} ({result['category_name']})")
        print(f"    이유: {result['reason']}")
        print(f"    폴더: {result['suggested_folder']}")
        print(f"    신뢰도: {result['confidence']:.2%}")

if __name__ == "__main__":
    test_classifier()


"""result_1

    ==================================================
    PARA 분류 테스트
    ==================================================

    📄 프로젝트_제안서.pdf
        카테고리: P (Projects)
        이유: 이 파일은 구체적인 목표와 기한이 있는 신규 프로젝트 제안서이기 때문에 프로젝트에 해당합니다.
        폴더: 프로젝트_제안서_2025
        신뢰도: 100.00%

    📄 Python_학습노트.md
        카테고리: A (Areas)
        이유: 파이썬 학습노트는 지속적으로 업데이트되고 있으며, 관심을 가지는 분야에 해당하기 때문입니다.
        폴더: Python_학습_영역
        신뢰도: 90.00%

    📄 AI_논문_모음.pdf
        카테고리: R (Resources)
        이유: AI 관련 논문 모음집은 나중에 참고할 수 있는 지식이나 정보로 분류됩니다.
        폴더: AI_자료_참고
        신뢰도: 90.00%

    📄 2024_완료_프로젝트.pdf
        카테고리: AR (Archives)
        이유: 2024년에 완료된 프로젝트에 대한 최종 보고서로, 더 이상 활성화되지 않은 항목이기 때문입니다.
        폴더: 완료된 프로젝트
        신뢰도: 100.00%

"""