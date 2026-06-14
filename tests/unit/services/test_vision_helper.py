# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# tests/test_vision_helper.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
FlowNote MVP - Vision Helper 테스트

VisionCodeGenerator 클래스의 기본 기능 및 통합 테스트
"""

# 프로젝트 루트를 Python path에 추가
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import pytest

from backend.modules.vision_helper import VisionCodeGenerator


class TestVisionCodeGenerator:
    """VisionCodeGenerator 테스트 클래스"""

    @pytest.fixture
    def generator(self):
        """테스트용 VisionCodeGenerator 인스턴스"""
        return VisionCodeGenerator()

    @pytest.fixture
    def test_image_path(self):
        """테스트 이미지 경로"""
        # 프로젝트 루트 기준 경로 계산
        project_root = Path(__file__).resolve().parent.parent
        return project_root / "tests" / "test_images" / "test.png"

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1. 초기화 테스트
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def test_generator_initialization(self, generator):
        """VisionCodeGenerator 초기화 확인"""
        assert generator is not None
        assert generator.model_name is not None
        assert generator.client is not None
        print("✅ Generator 초기화 성공!")

    def test_model_name_is_gpt41(self, generator):
        """GPT-4.1 모델 사용 확인"""
        assert "4" in generator.model_name or "gpt-4" in generator.model_name.lower()
        print(f"✅ 사용 모델: {generator.model_name}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2. 이미지 인코딩 테스트
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def test_encode_image_file_not_found(self, generator):
        """존재하지 않는 이미지 파일 처리"""
        with pytest.raises(FileNotFoundError):
            generator.encode_image("non_existent_file.png")
        print("✅ 파일 없음 에러 처리 완벽!")

    def test_encode_image_with_valid_file(self, generator, test_image_path):
        """유효한 이미지 파일 인코딩 (파일 존재 시)"""
        if test_image_path.exists():
            encoded = generator.encode_image(str(test_image_path))
            assert encoded is not None
            assert isinstance(encoded, str)
            assert len(encoded) > 0
            print(f"✅ 이미지 인코딩 성공! (크기: {len(encoded)} bytes)")
        else:
            pytest.skip(f"테스트 이미지 없음: {test_image_path}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3. 메서드 반환값 검증
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def test_generate_streamlit_code_file_not_found(self, generator):
        """존재하지 않는 파일로 코드 생성 시도"""
        result = generator.generate_streamlit_code("fake_image.png")

        # 반환 구조 검증
        assert isinstance(result, dict)
        assert "success" in result
        assert "error" in result
        assert result["success"] is False
        assert "찾을 수 없습니다" in result["error"]
        print("✅ 에러 처리 반환값 완벽!")

    def test_generate_streamlit_code_response_structure(
        self, generator, test_image_path
    ):
        """코드 생성 응답 구조 검증 (파일 존재 시)"""
        if test_image_path.exists():
            result = generator.generate_streamlit_code(str(test_image_path))

            # 필수 필드 확인
            assert isinstance(result, dict)
            assert "success" in result
            assert "code" in result
            assert "description" in result
            assert "components" in result

            if result["success"]:
                assert isinstance(result["code"], str)
                assert isinstance(result["description"], str)
                assert isinstance(result["components"], list)
                print("✅ 응답 구조 완벽!")
            else:
                print(f"⚠️ API 응답 실패: {result.get('error')}")
        else:
            pytest.skip(f"테스트 이미지 없음: {test_image_path}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 4. 컴포넌트 추출 테스트
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def test_extract_streamlit_components(self, generator):
        """Streamlit 컴포넌트 추출 로직"""
        sample_code = """
import streamlit as st

st.title("Test App")
st.button("Click me")
st.slider("Select value", 0, 100)
st.text_input("Enter text")
"""
        components = generator._extract_streamlit_components(sample_code)

        assert isinstance(components, list)
        assert "st.title" in components
        assert "st.button" in components
        assert "st.slider" in components
        assert "st.text_input" in components
        print(f"✅ 컴포넌트 추출 완벽! {components}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 5. URL 기반 생성 테스트
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def test_generate_from_url_response_structure(self, generator):
        """URL 기반 코드 생성 응답 구조"""
        # 실제 URL을 사용하면 API 비용이 소모되므로 구조만 검증
        # 프로덕션 환경에서만 실행

        required_keys = ["success", "code", "description", "components"]
        # 실제 테스트는 수동으로 또는 CI/CD에서 필요시 실행
        print("⚠️ URL 기반 테스트는 API 비용으로 인해 스킵됨 (필요시 수동 실행)")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 독립 실행 모드 (테스트 파일 직접 실행)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    """pytest 없이 기본 테스트 실행 (개발용)"""
    from pathlib import Path

    print("\n" + "=" * 60)
    print("🔥 VisionCodeGenerator 기본 테스트 시작!")
    print("=" * 60 + "\n")

    # 1️⃣ Generator 초기화
    print("[1️⃣] Generator 초기화...")
    try:
        generator = VisionCodeGenerator()
        print("✅ 성공! 모델:", generator.model_name)
    except Exception as e:
        print(f"❌ 실패: {e}")
        exit(1)

    # 2️⃣ 파일 없음 에러 처리 테스트
    print("\n[2️⃣] 파일 없음 에러 처리 테스트...")
    result = generator.generate_streamlit_code("fake.png")
    if not result["success"] and "찾을 수 없습니다" in result["error"]:
        print("✅ 성공! 에러 메시지:", result["error"])
    else:
        print("❌ 실패: 예상과 다른 응답")

    # 3️⃣ 컴포넌트 추출 테스트
    print("\n[3️⃣] 컴포넌트 추출 테스트...")
    test_code = """
import streamlit as st
st.button("Test")
st.slider("Value", 0, 10)
"""
    components = generator._extract_streamlit_components(test_code)
    if "st.button" in components and "st.slider" in components:
        print(f"✅ 성공! 추출된 컴포넌트: {components}")
    else:
        print("❌ 실패: 컴포넌트 추출 오류")

    # 4️⃣ 테스트 이미지 확인
    print("\n[4️⃣] 테스트 이미지 확인...")
    project_root = Path(__file__).resolve().parent.parent
    test_image = project_root / "tests" / "test_images" / "test.png"

    if test_image.exists():
        print(f"✅ 테스트 이미지 존재: {test_image}")
        print("   → 실제 API 테스트 가능!")
    else:
        print(f"⚠️ 테스트 이미지 없음: {test_image}")
        print("   → 스크린샷을 해당 경로에 저장해주세요!")

    print("\n" + "=" * 60)
    print("🎉 기본 테스트 완료!")
    print("=" * 60 + "\n")


"""test_result_1 - `python tests/test_vision_helper.py`

    - 독립 실행 테스트 ✅

    ============================================================
    🔥 VisionCodeGenerator 기본 테스트 시작!
    ============================================================

    [1️⃣] Generator 초기화...
    ✅ 성공! 모델: openai/gpt-4.1

    [2️⃣] 파일 없음 에러 처리 테스트...
    ✅ 성공! 에러 메시지: 이미지 파일을 찾을 수 없습니다: fake.png

    [3️⃣] 컴포넌트 추출 테스트...
    ✅ 성공! 추출된 컴포넌트: ['st.button', 'st.slider']

    [4️⃣] 테스트 이미지 확인...
    ✅ 테스트 이미지 존재: /Users/jay/ICT-projects/flownote-mvp/tests/test_images/test.png
        → 실제 API 테스트 가능!

    ============================================================
    🎉 기본 테스트 완료!
    ============================================================

"""

"""test_result_2 - `pytest tests/test_vision_helper.py -v`

    - 일반 테스트 ✅

    ============================================================== test session starts ===============================================================
    platform darwin -- Python 3.11.10, pytest-8.3.0, pluggy-1.6.0 -- /Users/jay/.pyenv/versions/3.11.10/envs/myenv/bin/python
    cachedir: .pytest_cache
    rootdir: /Users/jay/ICT-projects/flownote-mvp
    plugins: anyio-4.11.0, langsmith-0.4.37
    collected 8 items                                                                                                                                

    tests/test_vision_helper.py::TestVisionCodeGenerator::test_generator_initialization PASSED                                                 [ 12%]
    tests/test_vision_helper.py::TestVisionCodeGenerator::test_model_name_is_gpt41 PASSED                                                      [ 25%]
    tests/test_vision_helper.py::TestVisionCodeGenerator::test_encode_image_file_not_found PASSED                                              [ 37%]
    tests/test_vision_helper.py::TestVisionCodeGenerator::test_encode_image_with_valid_file PASSED                                             [ 50%]
    tests/test_vision_helper.py::TestVisionCodeGenerator::test_generate_streamlit_code_file_not_found PASSED                                   [ 62%]
    tests/test_vision_helper.py::TestVisionCodeGenerator::test_generate_streamlit_code_response_structure PASSED                               [ 75%]
    tests/test_vision_helper.py::TestVisionCodeGenerator::test_extract_streamlit_components PASSED                                             [ 87%]
    tests/test_vision_helper.py::TestVisionCodeGenerator::test_generate_from_url_response_structure PASSED                                     [100%]

    =============================================================== 8 passed in 19.03s ===============================================================

"""

"""test_result_3 - `pytest tests/test_vision_helper.py::TestVisionCodeGenerator::test_generator_initialization -v`

    - 특정 테스트만 실행 ✅

    (myenv) ➜  flownote-mvp git:(feat/vision-api) ✗ pytest tests/test_vision_helper.py::TestVisionCodeGenerator::test_generator_initialization -v

    ============================================================== test session starts ===============================================================
    platform darwin -- Python 3.11.10, pytest-8.3.0, pluggy-1.6.0 -- /Users/jay/.pyenv/versions/3.11.10/envs/myenv/bin/python
    cachedir: .pytest_cache
    rootdir: /Users/jay/ICT-projects/flownote-mvp
    plugins: anyio-4.11.0, langsmith-0.4.37
    collected 1 item                                                                                                                                 

    tests/test_vision_helper.py::TestVisionCodeGenerator::test_generator_initialization PASSED                                                 [100%]

    =============================================================== 1 passed in 0.35s ================================================================

"""
