# tests/unit/services/test_file_access_logger.py

import pytest
import csv
import os
from pathlib import Path
from backend.services.file_access_logger import FileAccessLogger


@pytest.fixture
def test_logger(tmp_path):
    """
    테스트용 Logger fixture.
    tmp_path를 사용하여 격리된 환경에서 테스트 수행.
    """
    # log_dir은 프로젝트 루트 기준이지만,
    # 테스트를 위해 임시 경로를 주입할 수 있어야 함.
    # 하지만 현재 구현은 project_root 기준으로 경로를 잡음.
    # 이를 우회하기 위해 FileAccessLogger가 절대 경로를 받을 수 있게 하거나
    # log_dir을 조작해야 함.

    # 더 좋은 방법: FileAccessLogger의 __init__에서 project_root를 override 할 수 있게 하거나
    # log_path를 직접 설정하는 것.
    # 여기서는 __init__ 수정 없이 log_dir을 상대 경로로 잘 맞춰서 tmp_path에 생성되게 하기는 어려움 (project_root가 고정).
    # 따라서, 단순하게 FileAccessLogger를 상속받거나 경로를 monkeypatch 하는 것이 좋음.

    # 하지만 가장 깔끔한 건 생성자에서 absolute path 지원 여부를 확인하는 것.
    # 현재 구현: self.log_path = self.project_root / log_dir / log_file

    # 테스트를 위해 FileAccessLogger를 약간 수정하는 것이 낫겠지만,
    # 이미 구현된 코드를 수정하기보다 테스트에서 log_path 속성을 덮어쓰는 방식을 사용.

    logger = FileAccessLogger(log_dir="temp_test_data", log_file="test_log.csv")

    # log_path를 tmp_path 내부로 강제 변경
    logger.log_path = tmp_path / "test_log.csv"
    logger._ensure_log_file()  # 변경된 경로에 다시 생성

    return logger


def test_initialization(test_logger):
    """초기화 시 로그 파일 생성 확인"""
    assert test_logger.log_path.exists()

    with open(test_logger.log_path, "r") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert header == ["timestamp", "file_path", "access_type"]


def test_log_access(test_logger):
    """로그 기록 테스트"""
    success = test_logger.log_access("doc1.md", "read")
    assert success is True

    with open(test_logger.log_path, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["file_path"] == "doc1.md"
        assert rows[0]["access_type"] == "read"
        assert "timestamp" in rows[0]


def test_get_file_stats(test_logger):
    """통계 조회 테스트"""
    test_logger.log_access("doc1.md", "read")
    test_logger.log_access("doc1.md", "write")
    test_logger.log_access("doc1.md", "read")

    stats = test_logger.get_file_stats("doc1.md")

    assert stats["access_count"] == 3
    assert stats["access_types"]["read"] == 2
    assert stats["access_types"]["write"] == 1
    assert stats["last_accessed"] is not None


def test_get_top_accessed_files(test_logger):
    """상위 파일 조회 테스트"""
    # doc1: 3회
    for _ in range(3):
        test_logger.log_access("doc1.md")

    # doc2: 5회
    for _ in range(5):
        test_logger.log_access("doc2.md")

    # doc3: 1회
    test_logger.log_access("doc3.md")

    top_files = test_logger.get_top_accessed_files(limit=2)

    assert len(top_files) == 2
    assert top_files[0]["file_path"] == "doc2.md"
    assert top_files[0]["count"] == 5
    assert top_files[1]["file_path"] == "doc1.md"
    assert top_files[1]["count"] == 3


def test_stats_empty_log(test_logger):
    """로그가 없을 때 통계 조회"""
    # 파일은 존재하지만 내용은 헤더뿐
    stats = test_logger.get_file_stats("non_existent.md")
    assert stats["access_count"] == 0

    top_files = test_logger.get_top_accessed_files()
    assert top_files == []
