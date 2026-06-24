"""
Tests for Phase 3: Docker Sandbox + Static Analysis tools.

Tests cover:
    - LintFinding / SandboxResult models
    - DockerSandbox availability check
    - StaticAnalyzer runner selection and aggregation
    - Individual runner output parsers (without running actual tools)
    - AgenticExecutor script validation (banned imports, syntax)
    - SandboxResult helper methods
"""

import json
import textwrap
import pytest
from unittest.mock import MagicMock, patch

from analyzers.models import (
    LintFinding, SandboxResult, Severity, ToolRunResult,
)


# ── Model Tests ─────────────────────────────────────────────────────────


class TestLintFinding:
    def test_defaults(self):
        finding = LintFinding(tool="ruff", file_path="utils.py")
        assert finding.line == 0
        assert finding.severity == Severity.NOTE   # actual default is NOTE
        assert finding.message == ""

    def test_severity_enum(self):
        finding = LintFinding(
            tool="bandit", file_path="api.py",
            line=42, severity=Severity.ERROR,
            rule_id="B101", message="assert used",
        )
        assert finding.severity == Severity.ERROR
        assert finding.severity.value == "ERROR"  # enum values are uppercase


class TestToolRunResult:
    def test_success_result(self):
        result = ToolRunResult(
            tool="ruff",
            success=True,
            findings=[
                LintFinding(tool="ruff", file_path="a.py", line=1,
                            severity=Severity.ERROR, rule_id="E501",
                            message="Line too long"),
            ],
            duration_seconds=0.5,
        )
        assert result.success is True
        assert len(result.findings) == 1

    def test_error_result(self):
        result = ToolRunResult(
            tool="semgrep",
            success=False,
            error="semgrep not installed",
            exit_code=-2,
        )
        assert result.success is False
        assert result.findings == []


class TestSandboxResult:
    def _make_result(self):
        findings = [
            LintFinding(tool="ruff", file_path="a.py", line=10,
                        severity=Severity.ERROR, rule_id="E501",
                        message="Line too long"),
            LintFinding(tool="bandit", file_path="b.py", line=20,
                        severity=Severity.ERROR, rule_id="B101",
                        message="Assert used"),
            LintFinding(tool="ruff", file_path="a.py", line=5,
                        severity=Severity.WARNING, rule_id="W291",
                        message="Trailing whitespace"),
        ]
        return SandboxResult(
            files_analyzed=["a.py", "b.py"],
            all_findings=findings,
            tool_results=[
                ToolRunResult(tool="ruff", success=True, findings=findings[:2]),
                ToolRunResult(tool="bandit", success=True, findings=findings[2:]),
            ],
        )

    def test_error_count(self):
        result = self._make_result()
        assert result.error_count() == 2

    def test_warning_count(self):
        result = self._make_result()
        assert result.warning_count() == 1

    def test_findings_by_file(self):
        result = self._make_result()
        by_file = result.findings_by_file()
        assert "a.py" in by_file
        assert "b.py" in by_file
        assert len(by_file["a.py"]) == 2

    def test_findings_by_severity(self):
        result = self._make_result()
        by_sev = result.findings_by_severity()
        assert "error" in by_sev or Severity.ERROR in by_sev or "ERROR" in by_sev
        errors = by_sev.get("error") or by_sev.get(Severity.ERROR) or by_sev.get("ERROR", [])
        assert len(errors) == 2

    def test_to_summary_string(self):
        result = self._make_result()
        summary = result.to_summary_string()
        assert isinstance(summary, str)
        assert len(summary) > 0


# ── Docker Sandbox Tests ─────────────────────────────────────────────────


class TestDockerSandbox:
    def test_init_defaults(self):
        from analyzers.docker_sandbox import DockerSandbox
        sandbox = DockerSandbox()
        assert sandbox.memory == DockerSandbox.DEFAULT_MEMORY
        assert sandbox.timeout == DockerSandbox.DEFAULT_TIMEOUT
        assert sandbox.network == "none"

    def test_init_custom(self):
        from analyzers.docker_sandbox import DockerSandbox
        sandbox = DockerSandbox(memory="256m", timeout=60, cpus="0.5")
        assert sandbox.memory == "256m"
        assert sandbox.timeout == 60

    @patch("subprocess.run")
    def test_is_available_docker_present(self, mock_run):
        from analyzers.docker_sandbox import DockerSandbox
        mock_run.return_value = MagicMock(returncode=0)
        sandbox = DockerSandbox()
        assert sandbox.is_available() is True

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_is_available_docker_missing(self, mock_run):
        from analyzers.docker_sandbox import DockerSandbox
        sandbox = DockerSandbox()
        assert sandbox.is_available() is False


# ── Runner Parser Tests ─────────────────────────────────────────────────


class TestRuffRunner:
    def _get_runner(self):
        from analyzers.tool_runners.ruff_runner import RuffRunner
        return RuffRunner()

    def test_parse_valid_json(self):
        runner = self._get_runner()
        raw = json.dumps([
            {
                "filename": "utils.py",
                "location": {"row": 10, "column": 5},
                "code": "E501",
                "message": "Line too long (120 > 88)",
                "fix": None,
            },
            {
                "filename": "api.py",
                "location": {"row": 5, "column": 1},
                "code": "F401",
                "message": "'os' imported but unused",
                "fix": None,
            },
        ])
        findings = runner.parse_output(raw, "/repo")
        assert len(findings) == 2
        assert findings[0].file_path == "utils.py"
        assert findings[0].line == 10
        assert findings[0].rule_id == "E501"
        assert findings[1].rule_id == "F401"

    def test_parse_empty_output(self):
        runner = self._get_runner()
        findings = runner.parse_output("[]", "/repo")
        assert findings == []

    def test_parse_invalid_json(self):
        runner = self._get_runner()
        findings = runner.parse_output("not json", "/repo")
        assert isinstance(findings, list)

    def test_severity_mapping_error(self):
        runner = self._get_runner()
        raw = json.dumps([{
            "filename": "x.py", "location": {"row": 1, "column": 1},
            "code": "E101", "message": "error", "fix": None,
        }])
        findings = runner.parse_output(raw, "/repo")
        assert findings[0].severity == Severity.ERROR

    def test_severity_mapping_warning(self):
        runner = self._get_runner()
        raw = json.dumps([{
            "filename": "x.py", "location": {"row": 1, "column": 1},
            "code": "W291", "message": "trailing whitespace", "fix": None,
        }])
        findings = runner.parse_output(raw, "/repo")
        assert findings[0].severity == Severity.WARNING


class TestBanditRunner:
    def _get_runner(self):
        from analyzers.tool_runners.bandit_runner import BanditRunner
        return BanditRunner()

    def test_parse_valid_json(self):
        runner = self._get_runner()
        raw = json.dumps({
            "results": [
                {
                    "filename": "auth.py",
                    "line_number": 42,
                    "test_id": "B101",
                    "issue_text": "Use of assert detected",
                    "issue_severity": "HIGH",
                    "issue_confidence": "HIGH",
                }
            ]
        })
        findings = runner.parse_output(raw, "/repo")
        assert len(findings) == 1
        assert findings[0].severity == Severity.ERROR
        assert findings[0].rule_id == "B101"
        assert findings[0].line == 42

    def test_severity_high_is_error(self):
        runner = self._get_runner()
        raw = json.dumps({"results": [{
            "filename": "a.py", "line_number": 1,
            "test_id": "B102", "issue_text": "High risk",
            "issue_severity": "HIGH", "issue_confidence": "HIGH",
        }]})
        findings = runner.parse_output(raw, "/repo")
        assert findings[0].severity == Severity.ERROR

    def test_severity_medium_is_warning(self):
        runner = self._get_runner()
        raw = json.dumps({"results": [{
            "filename": "a.py", "line_number": 1,
            "test_id": "B201", "issue_text": "Medium risk",
            "issue_severity": "MEDIUM", "issue_confidence": "MEDIUM",
        }]})
        findings = runner.parse_output(raw, "/repo")
        assert findings[0].severity == Severity.WARNING

    def test_empty_results(self):
        runner = self._get_runner()
        findings = runner.parse_output(json.dumps({"results": []}), "/repo")
        assert findings == []


class TestPipAuditRunner:
    def _get_runner(self):
        from analyzers.tool_runners.pip_audit_runner import PipAuditRunner
        return PipAuditRunner()

    def test_parse_vulnerabilities(self):
        runner = self._get_runner()
        raw = json.dumps({
            "dependencies": [
                {
                    "name": "requests",
                    "version": "2.25.0",
                    "vulns": [
                        {
                            "id": "CVE-2021-12345",
                            "fix_versions": ["2.26.0"],
                            "description": "SSRF vulnerability",
                        }
                    ],
                },
                {
                    "name": "numpy",
                    "version": "1.21.0",
                    "vulns": [],
                },
            ]
        })
        findings = runner.parse_output(raw, "/repo")
        assert len(findings) == 1
        assert findings[0].severity == Severity.ERROR
        assert "CVE-2021-12345" in findings[0].rule_id
        assert "requests" in findings[0].message

    def test_no_vulnerabilities(self):
        runner = self._get_runner()
        raw = json.dumps({"dependencies": [
            {"name": "flask", "version": "2.0.0", "vulns": []},
        ]})
        findings = runner.parse_output(raw, "/repo")
        assert findings == []


class TestTrivyRunner:
    def _get_runner(self):
        from analyzers.tool_runners.trivy_runner import TrivyRunner
        return TrivyRunner()

    def test_parse_vulnerabilities(self):
        runner = self._get_runner()
        raw = json.dumps({
            "Results": [
                {
                    "Target": "requirements.txt",
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": "CVE-2022-99999",
                            "PkgName": "pillow",
                            "InstalledVersion": "8.0.0",
                            "FixedVersion": "9.0.0",
                            "Severity": "CRITICAL",
                            "Description": "Image parsing vulnerability",
                        }
                    ],
                }
            ]
        })
        findings = runner.parse_output(raw, "/repo")
        assert len(findings) == 1
        assert findings[0].severity == Severity.ERROR
        assert findings[0].file_path == "requirements.txt"

    def test_severity_mapping(self):
        runner = self._get_runner()
        raw = json.dumps({"Results": [{
            "Target": "go.sum",
            "Vulnerabilities": [
                {"VulnerabilityID": "CVE-1", "PkgName": "pkg", "InstalledVersion": "1.0",
                 "FixedVersion": "2.0", "Severity": "HIGH", "Description": "..."},
                {"VulnerabilityID": "CVE-2", "PkgName": "pkg2", "InstalledVersion": "1.0",
                 "FixedVersion": "2.0", "Severity": "MEDIUM", "Description": "..."},
                {"VulnerabilityID": "CVE-3", "PkgName": "pkg3", "InstalledVersion": "1.0",
                 "FixedVersion": "2.0", "Severity": "LOW", "Description": "..."},
            ]
        }]})
        findings = runner.parse_output(raw, "/repo")
        assert len(findings) == 3
        assert findings[0].severity == Severity.ERROR    # HIGH
        assert findings[1].severity == Severity.WARNING   # MEDIUM
        assert findings[2].severity == Severity.NOTE      # LOW


# ── AgenticExecutor Tests ────────────────────────────────────────────────


class TestAgenticExecutor:
    def _get_executor(self):
        from analyzers.agentic_executor import AgenticExecutor
        return AgenticExecutor()

    def test_validate_clean_script(self):
        executor = self._get_executor()
        script = textwrap.dedent("""\
            import ast
            import json

            findings = []
            # Simple analysis
            print(json.dumps(findings))
        """)
        is_valid, reason = executor.validate_script(script)
        assert is_valid is True

    def test_validate_banned_import_os(self):
        executor = self._get_executor()
        script = "import os\nprint(os.listdir('/'))"
        is_valid, reason = executor.validate_script(script)
        assert is_valid is False
        assert "os" in reason.lower() or "banned" in reason.lower()

    def test_validate_banned_import_subprocess(self):
        executor = self._get_executor()
        script = "import subprocess\nsubprocess.run(['rm', '-rf', '/'])"
        is_valid, reason = executor.validate_script(script)
        assert is_valid is False

    def test_validate_eval_usage(self):
        executor = self._get_executor()
        script = "result = eval('1 + 1')"
        is_valid, reason = executor.validate_script(script)
        assert is_valid is False

    def test_validate_exec_usage(self):
        executor = self._get_executor()
        script = "exec('import os')"
        is_valid, reason = executor.validate_script(script)
        assert is_valid is False

    def test_validate_syntax_error(self):
        executor = self._get_executor()
        script = "def broken(:\n    pass"
        is_valid, reason = executor.validate_script(script)
        assert is_valid is False

    def test_validate_too_long(self):
        executor = self._get_executor()
        # 201 lines
        script = "\n".join(["# line" for _ in range(201)])
        is_valid, reason = executor.validate_script(script)
        assert is_valid is False

    def test_parse_valid_output(self):
        executor = self._get_executor()
        output = json.dumps({
            "file": "utils.py",
            "line": 10,
            "severity": "error",
            "message": "Potential bug detected",
        })
        findings = executor._parse_script_output(output)
        assert len(findings) == 1
        assert findings[0].line == 10
        assert findings[0].severity == Severity.ERROR

    def test_parse_invalid_output(self):
        executor = self._get_executor()
        findings = executor._parse_script_output("not json at all")
        assert isinstance(findings, list)


# ── StaticAnalyzer Tests ─────────────────────────────────────────────────


class TestStaticAnalyzer:
    def test_init(self):
        from analyzers.static_analyzer import StaticAnalyzer
        analyzer = StaticAnalyzer(max_workers=2)
        assert analyzer.max_workers == 2

    def test_select_python_runners(self):
        from analyzers.static_analyzer import StaticAnalyzer
        from analyzers.tool_runners.ruff_runner import RuffRunner
        from analyzers.tool_runners.bandit_runner import BanditRunner
        from unittest.mock import patch
        analyzer = StaticAnalyzer()
        # Patch is_available to return True for all runners
        with patch.object(RuffRunner, "is_available", return_value=True), \
             patch.object(BanditRunner, "is_available", return_value=True):
            runners = analyzer._select_runners("python", None)
        tool_names = [r.TOOL_NAME for r in runners]
        assert "ruff" in tool_names
        assert "bandit" in tool_names

    def test_select_with_filter(self):
        from analyzers.static_analyzer import StaticAnalyzer
        from analyzers.tool_runners.ruff_runner import RuffRunner
        from unittest.mock import patch
        analyzer = StaticAnalyzer()
        with patch.object(RuffRunner, "is_available", return_value=True):
            runners = analyzer._select_runners("python", ["ruff"])
        tool_names = [r.TOOL_NAME for r in runners]
        assert "ruff" in tool_names
        assert all(t == "ruff" for t in tool_names)

    def test_run_single_handles_exception(self):
        from analyzers.static_analyzer import StaticAnalyzer
        analyzer = StaticAnalyzer()
        mock_runner = MagicMock()
        mock_runner.TOOL_NAME = "test_tool"
        mock_runner.run.side_effect = RuntimeError("tool crashed")
        result = analyzer._run_single(mock_runner, "/tmp", None)
        assert result.success is False
        assert "crashed" in result.error or "test_tool" in result.error

    def test_analyze_returns_sandbox_result(self):
        from analyzers.static_analyzer import StaticAnalyzer
        analyzer = StaticAnalyzer()

        # Mock all runners to return empty ToolRunResults
        mock_runner = MagicMock()
        mock_runner.TOOL_NAME = "mock_tool"
        mock_runner.is_available.return_value = True
        mock_runner.run.return_value = ToolRunResult(
            tool="mock_tool", success=True, findings=[],
        )

        with patch.object(analyzer, "_select_runners", return_value=[mock_runner]):
            result = analyzer.analyze("/tmp")

        assert isinstance(result, SandboxResult)
