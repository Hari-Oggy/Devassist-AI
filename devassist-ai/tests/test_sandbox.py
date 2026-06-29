"""
Tests for DockerSandbox and AgenticExecutor.

All tests run without a real Docker daemon by mocking the docker-py client.
The AgenticExecutor tests also mock LLMRouter so no real API calls are made.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from analyzers.docker_sandbox import DockerSandbox, SandboxRunResult


# ── DockerSandbox ─────────────────────────────────────────────────────────


class TestDockerSandboxAvailability:
    def test_is_available_when_docker_up(self):
        sandbox = DockerSandbox()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.images.get.return_value = MagicMock()  # image exists

        with patch.object(sandbox, "_get_client", return_value=mock_client):
            assert sandbox.is_available() is True

    def test_is_available_returns_false_when_docker_missing(self):
        sandbox = DockerSandbox()
        with patch.object(sandbox, "_get_client", side_effect=Exception("No daemon")):
            assert sandbox.is_available() is False

    def test_is_available_returns_false_when_image_missing(self):
        sandbox = DockerSandbox()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.images.get.side_effect = Exception("Image not found")

        with patch.object(sandbox, "_get_client", return_value=mock_client):
            assert sandbox.is_available() is False


class TestDockerSandboxRunCommand:
    def _make_container_mock(self, exit_code=0, stdout=b'[]', stderr=b''):
        container = MagicMock()
        container.wait.return_value = {"StatusCode": exit_code}
        container.logs.side_effect = [stdout, stderr]
        return container

    def _patch_docker(self, sandbox, container_mock):
        """Patch both docker import AND _get_client so the code path is exercised."""
        mock_docker_module = MagicMock()
        mock_client = MagicMock()
        mock_client.containers.run.return_value = container_mock
        mock_docker_module.from_env.return_value = mock_client

        return (
            patch.dict("sys.modules", {"docker": mock_docker_module}),
            patch.object(sandbox, "_get_client", return_value=mock_client),
            mock_client,
        )

    def test_run_command_success(self):
        sandbox = DockerSandbox()
        container_mock = self._make_container_mock(
            exit_code=0,
            stdout=b'[{"file":"a.py","line":1,"severity":"error","message":"test"}]'
        )
        mock_docker_module = MagicMock()
        mock_client = MagicMock()
        mock_client.containers.run.return_value = container_mock

        with patch.dict("sys.modules", {"docker": mock_docker_module}), \
             patch.object(sandbox, "_get_client", return_value=mock_client):
            result = sandbox.run_command(
                command=["python", "/sandbox/script.py"],
                repo_path="/fake/repo",
            )

        assert result.success is True
        assert result.exit_code == 0

    def test_run_command_non_zero_exit(self):
        sandbox = DockerSandbox()
        container_mock = self._make_container_mock(exit_code=1, stdout=b'', stderr=b'SyntaxError')
        mock_docker_module = MagicMock()
        mock_client = MagicMock()
        mock_client.containers.run.return_value = container_mock

        with patch.dict("sys.modules", {"docker": mock_docker_module}), \
             patch.object(sandbox, "_get_client", return_value=mock_client):
            result = sandbox.run_command(
                command=["python", "/sandbox/script.py"],
                repo_path="/fake/repo",
            )

        assert result.success is False
        assert result.exit_code == 1

    def test_run_command_timeout(self):
        sandbox = DockerSandbox(timeout=1)
        container_mock = MagicMock()
        container_mock.wait.side_effect = Exception("Timed out")
        container_mock.logs.side_effect = [b'', b'']
        mock_docker_module = MagicMock()
        mock_client = MagicMock()
        mock_client.containers.run.return_value = container_mock

        with patch.dict("sys.modules", {"docker": mock_docker_module}), \
             patch.object(sandbox, "_get_client", return_value=mock_client):
            result = sandbox.run_command(
                command=["python", "/sandbox/script.py"],
                repo_path="/fake/repo",
                timeout=1,
            )

        assert result.timed_out is True
        assert result.success is False

    def test_run_command_docker_not_importable(self):
        sandbox = DockerSandbox()
        with patch.object(sandbox, "_get_client", side_effect=ImportError("No module docker")):
            result = sandbox.run_command(
                command=["python", "/sandbox/script.py"],
                repo_path="/fake/repo",
            )
        assert result.success is False
        assert result.error is not None

    def test_container_always_removed_on_success(self):
        sandbox = DockerSandbox()
        container_mock = self._make_container_mock(exit_code=0, stdout=b'[]')
        mock_docker_module = MagicMock()
        mock_client = MagicMock()
        mock_client.containers.run.return_value = container_mock

        with patch.dict("sys.modules", {"docker": mock_docker_module}), \
             patch.object(sandbox, "_get_client", return_value=mock_client):
            sandbox.run_command(command=["python", "x.py"], repo_path="/repo")

        container_mock.remove.assert_called_once_with(force=True)

    def test_container_always_removed_on_failure(self):
        sandbox = DockerSandbox()
        container_mock = MagicMock()
        container_mock.wait.side_effect = Exception("timeout")
        container_mock.logs.side_effect = [b'', b'']
        mock_docker_module = MagicMock()
        mock_client = MagicMock()
        mock_client.containers.run.return_value = container_mock

        with patch.dict("sys.modules", {"docker": mock_docker_module}), \
             patch.object(sandbox, "_get_client", return_value=mock_client):
            sandbox.run_command(command=["python", "x.py"], repo_path="/repo", timeout=1)

        container_mock.remove.assert_called_once_with(force=True)


# ── AgenticExecutor ───────────────────────────────────────────────────────


class TestAgenticExecutorValidation:
    def _make_executor(self):
        from analyzers.agentic_executor import AgenticExecutor
        mock_sandbox = MagicMock()
        mock_sandbox.is_available.return_value = True
        mock_router = MagicMock()
        return AgenticExecutor(sandbox=mock_sandbox, router=mock_router), mock_sandbox, mock_router

    def test_validate_script_allows_safe_code(self):
        from analyzers.agentic_executor import AgenticExecutor
        executor = AgenticExecutor.__new__(AgenticExecutor)
        safe_script = "import ast\nimport json\nprint(json.dumps([]))\n"
        assert executor._validate_script(safe_script) is None

    def test_validate_script_blocks_socket(self):
        from analyzers.agentic_executor import AgenticExecutor
        executor = AgenticExecutor.__new__(AgenticExecutor)
        bad = "import socket\ns = socket.socket()\n"
        assert executor._validate_script(bad) is not None

    def test_validate_script_blocks_subprocess(self):
        from analyzers.agentic_executor import AgenticExecutor
        executor = AgenticExecutor.__new__(AgenticExecutor)
        bad = "import subprocess\nsubprocess.run(['ls'])\n"
        assert executor._validate_script(bad) is not None

    def test_validate_script_blocks_file_write(self):
        from analyzers.agentic_executor import AgenticExecutor
        executor = AgenticExecutor.__new__(AgenticExecutor)
        bad = "with open('/etc/passwd', 'w') as f: f.write('pwned')\n"
        assert executor._validate_script(bad) is not None

    def test_validate_script_blocks_eval(self):
        from analyzers.agentic_executor import AgenticExecutor
        executor = AgenticExecutor.__new__(AgenticExecutor)
        bad = "eval('__import__(\"os\").system(\"rm -rf /\")')\n"
        assert executor._validate_script(bad) is not None

    def test_validate_script_blocks_too_many_lines(self):
        from analyzers.agentic_executor import AgenticExecutor
        executor = AgenticExecutor.__new__(AgenticExecutor)
        big = "\n".join(["x = 1"] * 201)
        assert executor._validate_script(big) is not None


class TestAgenticExecutorParsing:
    def test_parse_findings_valid_json(self):
        from analyzers.agentic_executor import AgenticExecutor
        executor = AgenticExecutor.__new__(AgenticExecutor)
        stdout = '[{"file":"a.py","line":10,"severity":"error","message":"SQL injection"}]'
        findings = executor._parse_findings(stdout)
        assert len(findings) == 1
        assert findings[0]["severity"] == "error"
        assert findings[0]["line"] == 10

    def test_parse_findings_empty_stdout(self):
        from analyzers.agentic_executor import AgenticExecutor
        executor = AgenticExecutor.__new__(AgenticExecutor)
        assert executor._parse_findings("") == []

    def test_parse_findings_no_json_array(self):
        from analyzers.agentic_executor import AgenticExecutor
        executor = AgenticExecutor.__new__(AgenticExecutor)
        assert executor._parse_findings("script completed OK\n") == []

    def test_parse_findings_ignores_non_dict_items(self):
        from analyzers.agentic_executor import AgenticExecutor
        executor = AgenticExecutor.__new__(AgenticExecutor)
        stdout = '[{"file":"a.py","line":1,"severity":"warning","message":"test"}, "bad"]'
        findings = executor._parse_findings(stdout)
        assert len(findings) == 1


class TestAgenticExecutorE2E:
    def test_execute_analysis_no_docker(self):
        from analyzers.agentic_executor import AgenticExecutor
        mock_sandbox = MagicMock()
        mock_sandbox.is_available.return_value = False
        executor = AgenticExecutor(sandbox=mock_sandbox, router=MagicMock())

        result = executor.execute_analysis(
            pr_diff="@@ -1,1 +1,1 @@ print('hello')",
            repo_path="/fake/repo",
            pr_number=42,
        )

        assert result.success is False
        assert result.sandbox_available is False
        assert "Docker" in result.error

    def test_execute_analysis_full_flow(self):
        from analyzers.agentic_executor import AgenticExecutor
        from llm.schemas import LLMResponse

        mock_sandbox = MagicMock()
        mock_sandbox.is_available.return_value = True
        
        # Sandbox returns findings JSON
        sandbox_result = MagicMock()
        sandbox_result.success = True
        sandbox_result.timed_out = False
        sandbox_result.error = None
        sandbox_result.stdout = '[{"file":"auth.py","line":5,"severity":"error","message":"SQL injection risk"}]'
        sandbox_result.stderr = ""
        sandbox_result.exit_code = 0
        sandbox_result.duration_seconds = 1.2
        mock_sandbox.run_command.return_value = sandbox_result

        mock_router = MagicMock()
        mock_router.generate.return_value = LLMResponse(
            success=True,
            content="```python\nimport json\nprint(json.dumps([{\"file\": \"auth.py\", \"line\": 5, \"severity\": \"error\", \"message\": \"SQL injection risk\"}]))\n```",
            model="gpt-4o",
            provider="openai",
            tokens_input=100,
            tokens_output=50,
        )

        executor = AgenticExecutor(sandbox=mock_sandbox, router=mock_router)
        result = executor.execute_analysis(
            pr_diff="@@ -1,1 +1,1 @@ query = f'SELECT * FROM users WHERE id={user_id}'",
            repo_path="/fake/repo",
            pr_number=1,
        )

        assert result.success is True
        assert result.sandbox_available is True
        assert len(result.findings) == 1
        assert result.findings[0]["severity"] == "error"

    def test_to_markdown_with_findings(self):
        from analyzers.agentic_executor import AgenticAnalysisResult
        r = AgenticAnalysisResult(
            success=True,
            findings=[{"file": "auth.py", "line": 5, "severity": "error", "message": "SQL injection"}]
        )
        md = r.to_markdown()
        assert "Runtime Analysis Findings" in md
        assert "auth.py" in md

    def test_to_markdown_no_findings(self):
        from analyzers.agentic_executor import AgenticAnalysisResult
        r = AgenticAnalysisResult(success=True, findings=[])
        md = r.to_markdown()
        assert "no issues" in md

    def test_to_markdown_on_failure(self):
        from analyzers.agentic_executor import AgenticAnalysisResult
        r = AgenticAnalysisResult(success=False, error="Docker not running")
        md = r.to_markdown()
        assert "Docker not running" in md
