"""Configuration tests"""
import pytest
from app.core.config import get_settings


def test_settings_loaded():
    """Test that settings are loaded correctly"""
    settings = get_settings()
    assert settings is not None
    assert settings.environment is not None


def test_database_url_configured():
    """Test that database URL is configured"""
    settings = get_settings()
    assert settings.database_url is not None
    assert len(settings.database_url) > 0


def test_redis_url_configured():
    """Test that Redis URL is configured"""
    settings = get_settings()
    assert settings.redis_url is not None
    assert "redis://" in settings.redis_url


def test_ollama_configuration():
    """Test that Ollama is configured for tests"""
    settings = get_settings()
    assert settings.llm_provider == "ollama"
    assert settings.ollama_base_url is not None
    assert settings.ollama_model is not None
