"""
Tests for core config and settings.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.config import Settings


class TestSettingsDefaults:
    """Ensure critical settings have sensible defaults."""

    def test_max_diff_size_is_reasonable(self):
        s = Settings()
        assert s.MAX_DIFF_SIZE >= 5000, "MAX_DIFF_SIZE should be at least 5000"

    def test_review_temperature_in_range(self):
        s = Settings()
        assert 0.0 <= s.REVIEW_TEMPERATURE <= 1.0, "Temperature should be 0-1"

    def test_github_app_fields_optional(self):
        s = Settings()
        # These should be None/empty by default (not required)
        assert s.GITHUB_APP_ID is None or s.GITHUB_APP_ID == ""
        assert s.GITHUB_APP_INSTALLATION_ID is None or s.GITHUB_APP_INSTALLATION_ID == ""

    def test_api_host_and_port_set(self):
        s = Settings()
        assert s.API_HOST is not None
        assert s.API_PORT is not None
        assert isinstance(s.API_PORT, int)
