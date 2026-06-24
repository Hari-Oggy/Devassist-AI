"""
Tool runner registry.

Each runner implements BaseRunner and handles one static analysis tool.
The StaticAnalyzer uses this registry to run all applicable tools in parallel.
"""

from analyzers.tool_runners.base_runner import BaseRunner
from analyzers.tool_runners.ruff_runner import RuffRunner
from analyzers.tool_runners.bandit_runner import BanditRunner
from analyzers.tool_runners.mypy_runner import MypyRunner
from analyzers.tool_runners.semgrep_runner import SemgrepRunner
from analyzers.tool_runners.pip_audit_runner import PipAuditRunner
from analyzers.tool_runners.trivy_runner import TrivyRunner

# Tool runners applicable to Python projects
PYTHON_RUNNERS: list[type[BaseRunner]] = [
    RuffRunner,
    BanditRunner,
    MypyRunner,
    PipAuditRunner,
]

# All available runners (multi-language + security)
ALL_RUNNERS: list[type[BaseRunner]] = [
    RuffRunner,
    BanditRunner,
    MypyRunner,
    SemgrepRunner,
    PipAuditRunner,
    TrivyRunner,
]

__all__ = [
    "BaseRunner",
    "RuffRunner",
    "BanditRunner",
    "MypyRunner",
    "SemgrepRunner",
    "PipAuditRunner",
    "TrivyRunner",
    "PYTHON_RUNNERS",
    "ALL_RUNNERS",
]
