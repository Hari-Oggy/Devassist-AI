"""Repository access utility for CodeGraph analysis.

:class:`RepoCloner` abstracts away the difference between a local workspace
and a remote Git repository so that :class:`~codegraph.graph_builder.CodeGraphBuilder`
always receives a plain filesystem path regardless of where the source lives.

Priority chain for :meth:`RepoCloner.get_repo_path`:

1. ``local_path`` supplied to the constructor.
2. ``CODEBASE_PATH`` setting from :func:`core.config.get_settings`.
3. A shallow Git clone of ``repo_url`` into a temporary directory.

:class:`RepoCloner` implements the context-manager protocol so temporary
directories are cleaned up automatically::

    with RepoCloner(repo_url="https://github.com/org/repo") as cloner:
        path  = cloner.get_repo_path()
        graph = CodeGraphBuilder(path).build()
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import hashlib
from typing import Optional
from filelock import FileLock

from core.config import get_settings
from core.logger import get_logger

logger = get_logger("codegraph.repo_cloner")

# Maximum wall-clock seconds allowed for a git clone operation
_CLONE_TIMEOUT_SECONDS: int = 120


class RepoCloner:
    """Manages read-only access to a repository for static analysis.

    The cloner resolves the source path using a three-tier priority strategy:

    1. **Explicit local path** — fastest; no I/O beyond what the caller already
       arranged.
    2. **``CODEBASE_PATH`` env setting** — allows the deployment environment to
       point at a pre-checked-out workspace.
    3. **Shallow Git clone** — falls back to cloning ``repo_url`` when no local
       path is available.  Clones use ``--depth 1`` to minimise bandwidth and
       disk usage.

    Temporary directories created by this class are tracked internally and
    removed by :meth:`cleanup` (or automatically on ``__exit__``).

    Args:
        repo_url: Optional HTTPS or SSH URL of the remote Git repository.
        local_path: Optional path to an already-checked-out local copy of the
            repository.  Takes highest priority.

    Example::

        with RepoCloner(repo_url="https://github.com/acme/service") as cloner:
            repo_path = cloner.get_repo_path()
            graph     = CodeGraphBuilder(repo_path).build()
    """

    def __init__(
        self,
        repo_url: Optional[str] = None,
        local_path: Optional[str] = None,
        branch: str = "HEAD",
        token: Optional[str] = None,
    ) -> None:
        self._repo_url: Optional[str] = repo_url
        self._local_path: Optional[str] = (
            os.path.abspath(local_path) if local_path else None
        )
        self._branch = branch
        self._token = token
        # All temp directories created by this instance (may be multiple if
        # clone_shallow is called more than once directly)
        self._temp_dirs: list[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_repo_path(self) -> str:
        """Resolve and return a filesystem path suitable for scanning.

        Resolution order:

        1. ``local_path`` given at construction time.
        2. ``CODEBASE_PATH`` from application settings (if non-empty and the
           path actually exists on disk).
        3. Shallow clone of :attr:`_repo_url` into a fresh temp directory.

        Returns:
            Absolute filesystem path to the repository root.

        Raises:
            ValueError: When no local path is configured *and* no ``repo_url``
                was provided, making it impossible to resolve a path.
            RuntimeError: When the shallow clone fails (propagated from
                :meth:`clone_shallow`).
        """
        # 1. Caller-supplied local path
        if self._local_path:
            logger.info(
                "Using caller-supplied local path",
                extra={"path": self._local_path},
            )
            return self._local_path

        # 2. CODEBASE_PATH from settings
        settings = get_settings()
        codebase_path: str = getattr(settings, "CODEBASE_PATH", "") or ""
        if codebase_path:
            expanded = os.path.abspath(codebase_path)
            if os.path.isdir(expanded):
                logger.info(
                    "Using CODEBASE_PATH from settings",
                    extra={"path": expanded},
                )
                return expanded
            logger.warning(
                f"CODEBASE_PATH '{expanded}' does not exist on disk — falling back to git clone. "
                "Fix: either create the directory, update CODEBASE_PATH in .env to a valid path, "
                "or clear it to always use git clone.",
            )

        # 3. Cache or Shallow clone
        if not self._repo_url:
            raise ValueError(
                "Cannot resolve a repository path: no local_path, no valid "
                "CODEBASE_PATH setting, and no repo_url was provided."
            )

        cache_base = getattr(settings, "REPO_CACHE_DIR", os.path.join(os.getcwd(), ".devassist_cache", "repos"))
        os.makedirs(cache_base, exist_ok=True)
        
        # Use a hash of the URL and branch to create a unique folder for the repo
        hash_input = f"{self._repo_url}:{self._branch}"
        repo_hash = hashlib.md5(hash_input.encode()).hexdigest()
        target_dir = os.path.join(cache_base, repo_hash)
        lock_path = target_dir + ".lock"
        
        with FileLock(lock_path, timeout=_CLONE_TIMEOUT_SECONDS):
            if os.path.exists(os.path.join(target_dir, ".git")):
                logger.info(
                    "Using cached repository, fetching latest changes",
                    extra={"repo_url": self._repo_url, "target_dir": target_dir},
                )
                try:
                    cmd_fetch = ["git", "-C", target_dir, "fetch", "--depth", "1", "origin", self._branch]
                    subprocess.run(cmd_fetch, capture_output=True, text=True, timeout=_CLONE_TIMEOUT_SECONDS, check=True)
                    
                    cmd_reset = ["git", "-C", target_dir, "reset", "--hard", f"origin/{self._branch}"]
                    subprocess.run(cmd_reset, capture_output=True, text=True, timeout=_CLONE_TIMEOUT_SECONDS, check=True)
                    
                    return target_dir
                except Exception as e:
                    logger.warning(
                        "Failed to update cached repo, will re-clone",
                        extra={"error": str(e)}
                    )
                    shutil.rmtree(target_dir, ignore_errors=True)
            
            logger.info(
                "Shallow-cloning repository to cache",
                extra={"repo_url": self._repo_url, "target_dir": target_dir},
            )
            # We don't append to self._temp_dirs because we want to cache it
            return self.clone_shallow(self._repo_url, target_dir, branch=self._branch, token=self._token)

    def clone_shallow(
        self,
        repo_url: str,
        target_dir: str,
        branch: str = "HEAD",
        token: Optional[str] = None,
    ) -> str:
        """Perform a shallow ``git clone --depth 1`` into *target_dir*.

        The clone uses a ``timeout`` of :data:`_CLONE_TIMEOUT_SECONDS` seconds
        to guard against network hangs.

        Args:
            repo_url: HTTPS or SSH URL of the remote repository.
            target_dir: Local directory path where the clone will be placed.
                The directory is created by ``git clone`` itself; it must not
                already contain a ``.git`` folder.
            branch: Branch or ref to clone.  Defaults to ``"HEAD"`` (the
                repository's default branch).

        Returns:
            Absolute path to the cloned repository root (i.e. *target_dir*).

        Raises:
            RuntimeError: When ``git clone`` exits with a non-zero status or
                times out.
        """
        cmd = [
            "git",
            "clone",
            "--depth", "1",
            "--single-branch",
        ]
        log_cmd = list(cmd)
        
        if token:
            import base64
            auth_string = base64.b64encode(token.encode()).decode()
            cmd += ["-c", f"http.extraHeader=Authorization: Basic {auth_string}"]  
            log_cmd += ["-c", "http.extraHeader=Authorization: Basic ***"]
            
        if branch and branch != "HEAD":
            cmd += ["--branch", branch]
            log_cmd += ["--branch", branch]
            
        cmd += [repo_url, target_dir]
        log_cmd += [repo_url, target_dir]

        logger.info(
            "Running git clone",
            extra={"cmd": " ".join(log_cmd)},
        )

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=_CLONE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"git clone timed out after {_CLONE_TIMEOUT_SECONDS}s "
                f"for URL: {repo_url}"
            ) from exc
        except FileNotFoundError as exc:
            raise RuntimeError(
                "git executable not found. Ensure git is installed and on PATH."
            ) from exc

        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise RuntimeError(
                f"git clone failed (exit {result.returncode}) for {repo_url}:\n{stderr}"
            )

        logger.info(
            "git clone succeeded",
            extra={"repo_url": repo_url, "target_dir": target_dir},
        )
        return os.path.abspath(target_dir)

    def cleanup(self) -> None:
        """Remove all temporary directories created by this instance.

        Safe to call multiple times — already-removed directories are silently
        ignored.
        """
        for temp_dir in list(self._temp_dirs):
            if os.path.isdir(temp_dir):
                try:
                    def onerror(func, path, exc_info):
                        import stat
                        try:
                            os.chmod(path, stat.S_IWRITE)
                            func(path)
                        except Exception:
                            pass
                    shutil.rmtree(temp_dir, onerror=onerror)
                    logger.info(
                        "Removed temporary clone directory",
                        extra={"path": temp_dir},
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to remove temporary directory",
                        extra={"path": temp_dir, "error": str(exc)},
                    )
            self._temp_dirs.remove(temp_dir)

    # ------------------------------------------------------------------
    # Context-manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "RepoCloner":
        """Support usage as a context manager.

        Returns:
            ``self`` so callers can write ``with RepoCloner(...) as cloner:``.
        """
        return self

    def __exit__(self, *args: object) -> None:
        """Clean up temporary directories on context exit.

        Args:
            *args: Standard exception-info triple; not inspected.
        """
        self.cleanup()
