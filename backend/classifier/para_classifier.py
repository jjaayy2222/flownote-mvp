# backend/classifier/para_classifier.py (최종)

"""
PARA 시스템 기반 AI 파일 분류기
"""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from typing import Dict
import os
from dotenv import load_dotenv

load_dotenv()


class PARAClassifier:
    """PARA 시스템으로 파일 자동 분류"""
    
    CATEGORIES = {
        "P": "Projects",
        "A": "Areas", 
        "R": "Resources",
        "AR": "Archives"
    }
    
    PROMPT_TEMPLATE = """당신은 파일 정리 전문가입니다. 
다음 파일을 PARA 시스템에 따라 분류해주세요.

파일명: {filename}
파일 내용 (처음 1000자):
{content}

PARA 분류 기준:
- P (Projects): 구체적 목표가 있고 기한이 있는 프로젝트 관련 파일
- A (Areas): 지속적으로 관심을 가지는 분야나 책임 영역
- R (Resources): 나중에 참고할 수 있는 지식이나 정보
- AR (Archives): 완료되었거나 더 이상 활성화되지 않은 항목

다음 형식으로 정확히 답변하세요:
카테고리: [P/A/R/AR 중 하나만]
이유: [한 문장으로 분류 근거 설명]
제안 폴더: [구체적인 폴더명, 한글 가능]
신뢰도: [0.0~1.0 사이 숫자]
"""
    
# backend/classifier/para_classifier.py (완전 수정!)

"""
PARA 시스템 기반 AI 파일 분류기
"""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from typing import Dict
import os
from dotenv import load_dotenv

load_dotenv()


class PARAClassifier:
    """PARA 시스템으로 파일 자동 분류"""
    
    CATEGORIES = {
        "P": "Projects",
        "A": "Areas", 
        "R": "Resources",
        "AR": "Archives"
    }
    
    PROMPT_TEMPLATE = """당신은 파일 정리 전문가입니다. 
다음 파일을 PARA 시스템에 따라 분류해주세요.

파일명: {filename}
파일 내용 (처음 1000자):
{content}

PARA 분류 기준:
- P (Projects): 구체적 목표가 있고 기한이 있는 프로젝트 관련 파일
- A (Areas): 지속적으로 관심을 가지는 분야나 책임 영역
- R (Resources): 나중에 참고할 수 있는 지식이나 정보
- AR (Archives): 완료되었거나 더 이상 활성화되지 않은 항목

다음 형식으로 정확히 답변하세요:
카테고리: [P/A/R/AR 중 하나만]
이유: [한 문장으로 분류 근거 설명]
제안 폴더: [구체적인 폴더명, 한글 가능]
신뢰도: [0.0~1.0 사이 숫자]
"""
    
    def __init__(self, model_type: str = "gpt4o_mini"):
        """
        Args:
            model_type: "gpt4o" 또는 "gpt4o_mini"
        """
        # .env에서 직접 API 설정 가져오기
        if model_type == "gpt4o":
            api_key = os.getenv("GPT4O_API_KEY")
            base_url = os.getenv("GPT4O_BASE_URL")
            model = os.getenv("GPT4O_MODEL", "gpt-4o")
        else:  # gpt4o_mini
            api_key = os.getenv("GPT4O_MINI_API_KEY")
            base_url = os.getenv("GPT4O_MINI_BASE_URL")
            model = os.getenv("GPT4O_MINI_MODEL", "gpt-4o-mini")
        
        if not api_key:
            raise ValueError(f"{model_type} API 키가 .env에 없습니다!")
        
        if not base_url:
            raise ValueError(f"{model_type} BASE URL이 .env에 없습니다!")
        
        # LangChain ChatOpenAI 초기화
        self.llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0.3,
            max_tokens=500
        )
        
        self.prompt = ChatPromptTemplate.from_template(self.PROMPT_TEMPLATE)
        self.chain = self.prompt | self.llm | StrOutputParser()
    
    def classify(self, filename: str, content: str) -> Dict:
        """파일 분류"""
        try:
            response = self.chain.invoke({
                "filename": filename,
                "content": content[:1000]
            })
            
            parsed = self._parse_response(response)
            parsed["category_name"] = self.CATEGORIES.get(
                parsed["category"], "Unknown"
            )
            
            return parsed
            
        except Exception as e:
            return {
                "category": "R",
                "category_name": "Resources",
                "reason": f"오류: {str(e)}",
                "suggested_folder": "기타",
                "confidence": 0.0
            }
    
    def _parse_response(self, response: str) -> Dict:
        """응답 파싱"""
        lines = response.strip().split("\n")
        result = {
            "category": "R",
            "reason": "파싱 실패",
            "suggested_folder": "기타",
            "confidence": 0.0
        }
        
        for line in lines:
            if line.startswith("카테고리:"):
                category = line.split(":")[1].strip()
                for cat in ["AR", "P", "A", "R"]:
                    if cat in category.upper():
                        result["category"] = cat
                        break
            
            elif line.startswith("이유:"):
                result["reason"] = line.split(":", 1)[1].strip()
            
            elif line.startswith("제안 폴더:"):
                result["suggested_folder"] = line.split(":", 1)[1].strip()
            
            elif line.startswith("신뢰도:"):
                try:
                    result["confidence"] = float(
                        line.split(":")[1].strip()
                    )
                except:
                    result["confidence"] = 0.5
        
        return result
