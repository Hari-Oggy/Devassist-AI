"""
Tests for the unified linter dispatcher and LINTER_MAP.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.tools.linter_tool import (
    LINTER_MAP,
    LINTER_TOOLS,
    run_linter,
    pylint_analysis,
    eslint_analysis,
    checkstyle_analysis,
)


class TestLinterMap:
    """Verify extension → linter mapping is correct."""

    def test_python_maps_to_pylint(self):
        assert LINTER_MAP[".py"] == pylint_analysis

    def test_javascript_maps_to_eslint(self):
        assert LINTER_MAP[".js"] == eslint_analysis

    def test_typescript_maps_to_eslint(self):
        assert LINTER_MAP[".ts"] == eslint_analysis

    def test_jsx_maps_to_eslint(self):
        assert LINTER_MAP[".jsx"] == eslint_analysis

    def test_tsx_maps_to_eslint(self):
        assert LINTER_MAP[".tsx"] == eslint_analysis

    def test_java_maps_to_checkstyle(self):
        assert LINTER_MAP[".java"] == checkstyle_analysis

    def test_unsupported_extension_returns_none(self):
        assert LINTER_MAP.get(".rb") is None
        assert LINTER_MAP.get(".go") is None
        assert LINTER_MAP.get(".rs") is None


class TestRunLinterDispatcher:
    """Test the run_linter dispatcher function."""

    def test_unsupported_extension_returns_empty(self):
        """Files with no registered linter should return empty string."""
        result = run_linter("script.sh")
        assert result == ""

    def test_nonexistent_file_returns_string(self):
        """Non-existent files should be handled gracefully."""
        result = run_linter("/nonexistent/path/to/file.py")
        assert isinstance(result, str)


class TestLinterToolsList:
    """Verify LINTER_TOOLS includes all tools."""

    def test_all_three_tools_present(self):
        assert len(LINTER_TOOLS) == 3
        tool_names = {t.__name__ for t in LINTER_TOOLS}
        assert "pylint_analysis" in tool_names
        assert "eslint_analysis" in tool_names
        assert "checkstyle_analysis" in tool_names
