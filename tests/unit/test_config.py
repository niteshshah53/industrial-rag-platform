"""
Unit tests for the configuration layer.

These tests verify that:
  - Settings parses valid environment variables correctly
  - Validators reject invalid values with clear error messages
  - Derived properties return correct computed values
  - get_settings() caching works as expected

No external services required. No Docker needed.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


class TestSettingsDefaults:
    """Default values are sensible and match the architecture spec."""

    def test_default_llm_model(self):
        settings = Settings()
        assert settings.llm_model == "llama3.2:3b"

    def test_default_embedding_model(self):
        settings = Settings()
        assert settings.embedding_model == "nomic-embed-text"

    def test_default_embedding_dimensions(self):
        settings = Settings()
        assert settings.embedding_dimensions == 768

    def test_default_distance_metric(self):
        settings = Settings()
        assert settings.qdrant_distance_metric == "Cosine"

    def test_default_chunk_size_is_character_based(self):
        """chunk_size_chars must be >> 512 to avoid the token/char confusion bug."""
        settings = Settings()
        assert settings.chunk_size_chars >= 512, (
            "chunk_size_chars should be character-based (≥512); "
            "check you haven't set this to a token count by mistake."
        )

    def test_default_app_env(self):
        settings = Settings()
        assert settings.app_env == "development"


class TestDerivedProperties:
    """Derived properties compute correct values from raw settings."""

    def test_max_upload_size_bytes(self):
        settings = Settings(max_upload_size_mb=10)
        assert settings.max_upload_size_bytes == 10 * 1024 * 1024

    def test_is_production_false_in_development(self):
        settings = Settings(app_env="development")
        assert settings.is_production is False

    def test_is_production_true_in_production(self):
        settings = Settings(app_env="production")
        assert settings.is_production is True

    def test_qdrant_url_format(self):
        settings = Settings(qdrant_host="myhost", qdrant_port=9999)
        assert settings.qdrant_url == "http://myhost:9999"


class TestValidators:
    """Validators reject invalid values with informative errors."""

    def test_invalid_log_level_raises(self):
        with pytest.raises(ValidationError, match="log_level"):
            Settings(log_level="VERBOSE")

    def test_log_level_is_case_insensitive(self):
        settings = Settings(log_level="debug")
        assert settings.log_level == "DEBUG"

    def test_invalid_log_format_raises(self):
        with pytest.raises(ValidationError, match="log_format"):
            Settings(log_format="yaml")

    def test_invalid_distance_metric_raises(self):
        with pytest.raises(ValidationError, match="qdrant_distance_metric"):
            Settings(qdrant_distance_metric="L2")

    def test_score_threshold_above_one_raises(self):
        with pytest.raises(ValidationError, match="relevance_score_threshold"):
            Settings(relevance_score_threshold=1.5)

    def test_score_threshold_below_zero_raises(self):
        with pytest.raises(ValidationError, match="relevance_score_threshold"):
            Settings(relevance_score_threshold=-0.1)

    def test_score_threshold_boundary_values_accepted(self):
        assert Settings(relevance_score_threshold=0.0).relevance_score_threshold == 0.0
        assert Settings(relevance_score_threshold=1.0).relevance_score_threshold == 1.0


class TestGetSettings:
    """get_settings() returns a cached singleton."""

    def test_returns_settings_instance(self):
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_cached_returns_same_instance(self):
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
