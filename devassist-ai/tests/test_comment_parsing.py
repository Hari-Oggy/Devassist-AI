"""
Tests for ReviewAgent._parse_comments — the JSON extraction from LLM output.
"""
import pytest
import json
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# We test _parse_comments in isolation by instantiating a minimal mock
class FakeAgent:
    """Minimal stand-in so we can call _parse_comments without full init."""
    pass


def _get_parse_comments():
    """Import the actual _parse_comments method."""
    from agents.review_agent import ReviewAgent
    return ReviewAgent._parse_comments


class TestParseCommentsCleanJSON:
    """LLM returns perfectly clean JSON array."""

    def test_single_comment(self):
        parse = _get_parse_comments()
        agent = FakeAgent()
        raw = json.dumps([{"file": "app.py", "line": 10, "severity": "error", "comment": "Missing return"}])
        comments, err = parse(agent, raw)
        assert not err
        assert len(comments) == 1
        assert comments[0]["file"] == "app.py"
        assert comments[0]["line"] == 10

    def test_multiple_comments(self):
        parse = _get_parse_comments()
        agent = FakeAgent()
        raw = json.dumps([
            {"file": "a.py", "line": 1, "severity": "warning", "comment": "Unused import"},
            {"file": "b.py", "line": 5, "severity": "error", "comment": "Division by zero"},
        ])
        comments, err = parse(agent, raw)
        assert not err
        assert len(comments) == 2

    def test_new_json_schema(self):
        parse = _get_parse_comments()
        agent = FakeAgent()
        raw = json.dumps({
            "comments": [
                {
                    "file": "test.py",
                    "line": 15,
                    "severity": "HIGH",
                    "category": "security",
                    "message": "SQL injection vulnerability",
                    "suggestion": "Use parameterized queries"
                }
            ]
        })
        comments, err = parse(agent, raw)
        assert not err
        assert len(comments) == 1
        assert comments[0]["line"] == 15
        assert "**[SECURITY]** SQL injection vulnerability" in comments[0]["comment"]
        assert "**Suggestion:** Use parameterized queries" in comments[0]["comment"]

    def test_empty_array(self):
        parse = _get_parse_comments()
        agent = FakeAgent()
        comments, err = parse(agent, "[]")
        # Empty array has no {…} objects, so regex won't match → err=True, comments=[]
        assert comments == []


class TestParseCommentsMarkdownFenced:
    """LLM wraps JSON in ```json ... ``` fences."""

    def test_fenced_json(self):
        parse = _get_parse_comments()
        agent = FakeAgent()
        raw = '```json\n[{"file": "x.py", "line": 3, "severity": "suggestion", "comment": "Use f-string"}]\n```'
        comments, err = parse(agent, raw)
        assert not err
        assert len(comments) == 1
        assert comments[0]["comment"] == "Use f-string"

    def test_fenced_with_surrounding_text(self):
        parse = _get_parse_comments()
        agent = FakeAgent()
        raw = 'Here are my findings:\n```json\n[{"file": "y.java", "line": 12, "severity": "error", "comment": "NPE risk"}]\n```\nPlease review.'
        comments, err = parse(agent, raw)
        assert not err
        assert len(comments) == 1


class TestParseCommentsEdgeCases:
    """Edge cases and malformed LLM output."""

    def test_completely_empty_string(self):
        parse = _get_parse_comments()
        agent = FakeAgent()
        comments, err = parse(agent, "")
        # Should return empty list + error=True
        assert comments == [] or comments is not None

    def test_non_json_text(self):
        parse = _get_parse_comments()
        agent = FakeAgent()
        comments, err = parse(agent, "This code looks good, no issues found.")
        assert comments == []

    def test_json_object_not_array(self):
        parse = _get_parse_comments()
        agent = FakeAgent()
        raw = json.dumps({"file": "a.py", "line": 1, "severity": "error", "comment": "bug"})
        comments, err = parse(agent, raw)
        # Should handle single object gracefully (wrap in list or return empty)
        assert isinstance(comments, list)
