# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# backend/modules/vision_helper.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
FlowNote MVP - Vision API Helper Module

GPT-4.1 Vision API를 사용하여 이미지를 분석하고
Streamlit 코드를 자동 생성하는 모듈
"""

import base64
import re
from pathlib import Path
from typing import Any, Dict, Optional, Union

from backend.config import ModelConfig


class VisionCodeGenerator:
    """
    GPT-4.1 Vision API 기반 Streamlit 코드 생성기

    이미지를 분석하여 해당 UI를 재현하는 Streamlit 코드를 자동 생성
    """

    def __init__(self):
        """
        초기화: GPT-4.1 Vision API 클라이언트 생성
        """
        self.model_name = ModelConfig.GPT41_MODEL
        self.client = ModelConfig.get_openai_client(self.model_name)

        # 기본 시스템 프롬프트
        self.system_prompt = """
당신은 Streamlit UI 전문가입니다.
이미지를 보고 해당 UI를 재현하는 Streamlit 코드를 작성합니다.

코드 작성 규칙:
1. import streamlit as st로 시작
2. 실제 실행 가능한 코드만 작성
3. 주석은 한국어로 작성
4. UI 컴포넌트는 최대한 정확하게 재현
5. 코드는 `````` 블록으로 감싸기
        """.strip()

    def encode_image(self, image_path: Union[str, Path]) -> str:
        """
        이미지 파일을 base64로 인코딩

        Args:
            image_path: 이미지 파일 경로

        Returns:
            base64로 인코딩된 이미지 문자열

        Raises:
            FileNotFoundError: 이미지 파일이 존재하지 않을 때
        """
        image_path = Path(image_path)

        if not image_path.exists():
            raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")

        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def generate_streamlit_code(
        self,
        image_path: Union[str, Path],
        custom_prompt: Optional[str] = None,
        max_tokens: int = 2000,
    ) -> Dict[str, Any]:
        """
        이미지를 분석하여 Streamlit 코드 생성

        Args:
            image_path: 이미지 파일 경로
            custom_prompt: 사용자 지정 프롬프트 (선택)
            max_tokens: 최대 생성 토큰 수

        Returns:
            {
                "success": True/False,
                "code": "생성된 Streamlit 코드",
                "description": "코드 설명",
                "components": ["st.button", "st.slider", ...],
                "error": "에러 메시지 (실패 시)"
            }
        """
        try:
            # 이미지 인코딩
            base64_image = self.encode_image(image_path)

            # 사용자 프롬프트 구성
            user_prompt = custom_prompt if custom_prompt else """
이미지에 있는 UI를 Streamlit으로 재현하는 코드를 작성해주세요.

요구사항:
- 이미지의 레이아웃과 컴포넌트를 최대한 정확하게 재현
- 실제 실행 가능한 코드 작성
- 코드 설명 포함
- 사용된 Streamlit 컴포넌트 목록 제공
            """.strip()

            # GPT-4.1 Vision API 호출
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                },
                            },
                        ],
                    },
                ],
                max_tokens=max_tokens,
                temperature=0.7,
            )

            # 응답 파싱
            content = response.choices[0].message.content

            # 코드 추출 (`````` 블록에서)
            code_match = re.search(r"``````", content, re.DOTALL)
            code = code_match.group(1).strip() if code_match else content

            # Streamlit 컴포넌트 추출
            components = self._extract_streamlit_components(code)

            # 코드 설명 추출 (코드 블록 이전/이후 텍스트)
            description = re.sub(r"``````", "", content, flags=re.DOTALL).strip()

            return {
                "success": True,
                "code": code,
                "description": description,
                "components": components,
                "tokens_used": response.usage.total_tokens,
                "model": self.model_name,
            }

        except FileNotFoundError as e:
            return {
                "success": False,
                "error": str(e),
                "code": None,
                "description": None,
                "components": [],
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"코드 생성 중 오류 발생: {str(e)}",
                "code": None,
                "description": None,
                "components": [],
            }

    def _extract_streamlit_components(self, code: str) -> list:
        """
        코드에서 사용된 Streamlit 컴포넌트 추출

        Args:
            code: Streamlit 코드

        Returns:
            사용된 컴포넌트 목록 (예: ["st.button", "st.slider"])
        """
        # st.로 시작하는 메서드 호출 패턴 찾기
        pattern = r"st\.\w+"
        components = re.findall(pattern, code)

        # 중복 제거 & 정렬
        return sorted(set(components))

    def generate_from_url(
        self,
        image_url: str,
        custom_prompt: Optional[str] = None,
        max_tokens: int = 2000,
    ) -> Dict[str, Any]:
        """
        URL에서 이미지를 불러와 Streamlit 코드 생성

        Args:
            image_url: 이미지 URL (http/https)
            custom_prompt: 사용자 지정 프롬프트 (선택)
            max_tokens: 최대 생성 토큰 수

        Returns:
            generate_streamlit_code()와 동일한 형식
        """
        try:
            # 사용자 프롬프트 구성
            user_prompt = custom_prompt if custom_prompt else """
이미지에 있는 UI를 Streamlit으로 재현하는 코드를 작성해주세요.

요구사항:
- 이미지의 레이아웃과 컴포넌트를 최대한 정확하게 재현
- 실제 실행 가능한 코드 작성
- 코드 설명 포함
            """.strip()

            # GPT-4.1 Vision API 호출
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ],
                    },
                ],
                max_tokens=max_tokens,
                temperature=0.7,
            )

            # 응답 파싱 (위와 동일)
            content = response.choices[0].message.content
            code_match = re.search(r"``````", content, re.DOTALL)
            code = code_match.group(1).strip() if code_match else content
            components = self._extract_streamlit_components(code)
            description = re.sub(r"``````", "", content, flags=re.DOTALL).strip()

            return {
                "success": True,
                "code": code,
                "description": description,
                "components": components,
                "tokens_used": response.usage.total_tokens,
                "model": self.model_name,
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"코드 생성 중 오류 발생: {str(e)}",
                "code": None,
                "description": None,
                "components": [],
            }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 사용 예시 (테스트용)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    from pathlib import Path

    # 프로젝트 루트 기준 경로
    project_root = Path(__file__).resolve().parent.parent.parent
    test_image = project_root / "tests" / "test_images" / "test.png"

    generator = VisionCodeGenerator()
    result = generator.generate_streamlit_code(image_path=str(test_image))

    if result["success"]:
        print("✅ 코드 생성 성공!")
        print(f"\n📝 설명:\n{result['description']}\n")
        print(f"🔧 사용된 컴포넌트: {result['components']}\n")
        print(f"💻 생성된 코드:\n{result['code']}")
    else:
        print(f"❌ 실패: {result['error']}")
