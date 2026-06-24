"""
Docker Sandbox — runs analysis tools in isolated containers.

Provides a security boundary for running static analysis tools against
user code. Each sandbox run is disposable:
    - Read-only filesystem mount (--read-only)
    - No network access (--network=none)
    - Memory-limited (--memory=512m)
    - CPU-limited (--cpus=1.0)
    - Runs as non-root (--user 1000:1000)
    - Auto-removed on exit (--rm)
"""

from __future__ import annotations

import subprocess
from typing import Optional

from core.logger import get_logger

logger = get_logger("analyzers.docker_sandbox")


class DockerSandbox:
    """Isolated Docker container execution environment for static analysis.

    Each call to :meth:`run` spins up a fresh, disposable container,
    mounts the target directory read-only, and tears it down on exit.

    Example::

        sandbox = DockerSandbox()
        if sandbox.is_available():
            exit_code, stdout, stderr = sandbox.run(
                command=["ruff", "check", "--output-format", "json", "/workspace"],
                workdir="/local/path/to/repo",
            )
    """

    DEFAULT_IMAGE: str = "python:3.11-slim"
    DEFAULT_MEMORY: str = "512m"
    DEFAULT_CPUS: str = "1.0"
    DEFAULT_TIMEOUT: int = 120  # seconds

    def __init__(
        self,
        image: str = DEFAULT_IMAGE,
        memory: str = DEFAULT_MEMORY,
        cpus: str = DEFAULT_CPUS,
        timeout: int = DEFAULT_TIMEOUT,
        network: str = "none",
        read_only: bool = True,
    ) -> None:
        self.image = image
        self.memory = memory
        self.cpus = cpus
        self.timeout = timeout
        self.network = network
        self.read_only = read_only

    # ── Public API ──────────────────────────────────────────────────────

    def run(
        self,
        command: list[str],
        workdir: str,
        env: Optional[dict[str, str]] = None,
        extra_mounts: Optional[list[str]] = None,
    ) -> tuple[int, str, str]:
        """Run a command in an isolated Docker container.

        Args:
            command: The command + args to execute inside the container.
            workdir: Host-side path to mount at /workspace (read-only).
            env: Optional dict of environment variables to inject.
            extra_mounts: Optional list of ``"host:container:options"`` strings.

        Returns:
            Tuple of ``(exit_code, stdout, stderr)``.

        Raises:
            RuntimeError: If Docker is not installed or the daemon is unreachable.
        """
        docker_cmd = self._build_docker_cmd(command, workdir, env, extra_mounts)
        logger.debug("Running sandbox command: %s", " ".join(docker_cmd))

        try:
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            return result.returncode, result.stdout, result.stderr

        except FileNotFoundError as exc:
            raise RuntimeError(
                "Docker is not installed or not on PATH. "
                "Install Docker Desktop or Docker Engine to use the sandbox."
            ) from exc

        except subprocess.TimeoutExpired:
            logger.warning(
                "Docker sandbox timed out after %ds for command: %s",
                self.timeout, " ".join(command),
            )
            return -1, "", f"Sandbox timed out after {self.timeout}s"

        except Exception as exc:
            logger.error("Sandbox run error: %s", exc)
            return -3, "", str(exc)

    def is_available(self) -> bool:
        """Return True if the Docker daemon is reachable.

        Returns:
            ``True`` when ``docker info`` exits successfully.
        """
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    def pull_image_if_needed(self, image: str) -> bool:
        """Pull a Docker image if it is not already cached locally.

        Args:
            image: Full image reference, e.g. ``"python:3.11-slim"``.

        Returns:
            ``True`` on success, ``False`` on failure.
        """
        logger.info("Pulling Docker image: %s", image)
        try:
            result = subprocess.run(
                ["docker", "pull", image],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                logger.info("Image pulled successfully: %s", image)
                return True
            logger.warning("Failed to pull %s: %s", image, result.stderr)
            return False
        except Exception as exc:
            logger.error("Image pull error: %s", exc)
            return False

    # ── Private helpers ─────────────────────────────────────────────────

    def _build_docker_cmd(
        self,
        command: list[str],
        workdir: str,
        env: Optional[dict[str, str]],
        extra_mounts: Optional[list[str]],
    ) -> list[str]:
        """Assemble the full ``docker run`` command list."""
        cmd = [
            "docker", "run",
            "--rm",
            "--network", self.network,
            "--memory", self.memory,
            "--cpus", self.cpus,
            "--user", "1000:1000",
            "-v", f"{workdir}:/workspace:ro",
            "-w", "/workspace",
        ]

        if self.read_only:
            cmd.append("--read-only")

        # Extra bind mounts (e.g. for tool configs)
        for mount in (extra_mounts or []):
            cmd.extend(["-v", mount])

        # Environment variables
        for key, value in (env or {}).items():
            cmd.extend(["-e", f"{key}={value}"])

        cmd.append(self.image)
        cmd.extend(command)
        return cmd
