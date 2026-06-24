"""CodeGraph package — static analysis, dependency graphing, and impact analysis.

Modules:
    models         — Core dataclasses and enums (Symbol, Dependency, ChangeImpact, etc.)
    graph_builder  — CodeGraph container + CodeGraphBuilder for repo traversal
    impact_analyzer — ImpactAnalyzer that computes blast radius from a CodeGraph
    repo_cloner    — RepoCloner utility for local/remote repository access
"""

from codegraph.models import (
    Symbol,
    Dependency,
    ChangeImpact,
    ImpactReport,
    SymbolKind,
)
from codegraph.graph_builder import CodeGraph, CodeGraphBuilder
from codegraph.impact_analyzer import ImpactAnalyzer
from codegraph.repo_cloner import RepoCloner

__all__ = [
    "Symbol",
    "Dependency",
    "ChangeImpact",
    "ImpactReport",
    "SymbolKind",
    "CodeGraph",
    "CodeGraphBuilder",
    "ImpactAnalyzer",
    "RepoCloner",
]
