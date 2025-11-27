import pytest
from unittest.mock import MagicMock, patch
from backend.embedding import EmbeddingGenerator


@pytest.fixture
def mock_embedding_client():
    """Mock OpenAI embedding client"""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [
        MagicMock(embedding=[0.1] * 1536),
        MagicMock(embedding=[0.2] * 1536),
    ]
    mock_client.embeddings.create.return_value = mock_response
    return mock_client


def test_embedding_generator_init():
    """EmbeddingGenerator 초기화 테스트"""
    with patch("backend.embedding.ModelConfig.get_embedding_model") as mock_get_model:
        mock_get_model.return_value = MagicMock()
        generator = EmbeddingGenerator()
        assert generator.model_name is not None
        assert generator.client is not None


def test_generate_embeddings_empty_list(mock_embedding_client):
    """빈 텍스트 리스트 처리 테스트"""
    with patch(
        "backend.embedding.ModelConfig.get_embedding_model",
        return_value=mock_embedding_client,
    ):
        generator = EmbeddingGenerator()
        result = generator.generate_embeddings([])

        assert result["embeddings"] == []
        assert result["tokens"] == 0
        assert result["cost"] == 0.0


def test_generate_embeddings_success(mock_embedding_client):
    """정상 임베딩 생성 테스트"""
    with patch(
        "backend.embedding.ModelConfig.get_embedding_model",
        return_value=mock_embedding_client,
    ):
        with patch("backend.embedding.count_tokens", return_value=10):
            generator = EmbeddingGenerator()
            texts = ["Test text 1", "Test text 2"]
            result = generator.generate_embeddings(texts)

            assert len(result["embeddings"]) == 2
            assert result["tokens"] == 20  # 10 tokens * 2 texts
            assert result["cost"] > 0
            assert len(result["embeddings"][0]) == 1536


def test_generate_embeddings_cost_calculation(mock_embedding_client):
    """비용 계산 테스트"""
    with patch(
        "backend.embedding.ModelConfig.get_embedding_model",
        return_value=mock_embedding_client,
    ):
        with patch("backend.embedding.count_tokens", return_value=100):
            with patch(
                "backend.embedding.estimate_cost", return_value=0.002
            ) as mock_estimate:
                generator = EmbeddingGenerator()
                texts = ["Long text"]
                result = generator.generate_embeddings(texts)

                mock_estimate.assert_called_once()
                assert result["cost"] == 0.002
