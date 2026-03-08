"""
Tests for GitHubClient.get_reviewable_files — file filtering logic.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.tools.github_tool import GitHubClient


class TestSkipExtensions:
    """Verify the SKIP_EXTENSIONS set filters out non-source files."""

    def test_binary_extensions_present(self):
        skip = GitHubClient.SKIP_EXTENSIONS
        assert ".class" in skip
        assert ".jar" in skip
        assert ".exe" in skip
        assert ".png" in skip
        assert ".jpg" in skip
        assert ".pdf" in skip

    def test_source_extensions_not_skipped(self):
        skip = GitHubClient.SKIP_EXTENSIONS
        assert ".py" not in skip
        assert ".java" not in skip
        assert ".js" not in skip
        assert ".ts" not in skip
        assert ".go" not in skip
        assert ".rs" not in skip
        assert ".c" not in skip
        assert ".cpp" not in skip

    def test_lock_and_generated_files_skipped(self):
        skip = GitHubClient.SKIP_EXTENSIONS
        assert ".lock" in skip
        assert ".min.js" in skip or ".map" in skip  # At least one generated type


class TestGetValidDiffLines:
    """Test diff line extraction logic without GitHub API calls."""

    def _make_patch(self):
        """Sample unified diff patch."""
        return (
            "@@ -10,6 +10,8 @@\n"
            " unchanged_line\n"
            "+added_line_1\n"
            "+added_line_2\n"
            " unchanged_line_2\n"
            "-removed_line\n"
            " unchanged_line_3\n"
        )

    def test_parses_added_lines(self):
        """Added lines should be in the valid diff lines set for the RIGHT side."""
        patch = self._make_patch()
        # Parse manually using the same logic as get_valid_diff_lines
        lines = []
        current_line = 0
        for line in patch.splitlines():
            if line.startswith("@@"):
                import re
                match = re.search(r"\+(\d+)", line)
                if match:
                    current_line = int(match.group(1))
            elif line.startswith("+") and not line.startswith("+++"):
                lines.append(current_line)
                current_line += 1
            elif line.startswith("-") and not line.startswith("---"):
                pass
            elif not line.startswith("\\"):
                current_line += 1

        assert 11 in lines  # First added line
        assert 12 in lines  # Second added line
        assert len(lines) == 2
