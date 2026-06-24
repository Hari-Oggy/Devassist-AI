"""
History Indexer — Project Memory for DevAssist-AI Phase 4.

Maintains a persistent, searchable store of past PR reviews. When a new
PR arrives, the system retrieves semantically similar past reviews to
provide richer context to the LLM (e.g., "We saw this pattern in PR #42
and recommended X. The fix was merged.").

Storage format:
    JSONL file — one JSON object per line, each representing one review.
    The JSONL is also indexed in a lightweight FAISS vector store for
    semantic search over past review comments.

Entry schema:
    {
        "pr_number": 42,
        "repo": "owner/repo",
        "timestamp": "2024-01-01T12:00:00Z",
        "title": "Add user authentication",
        "diff_summary": "...",          # short summary of the diff
        "findings": [...],              # list of finding dicts
        "reviewer_comments": [...],     # human reviewer comments (if any)
        "resolution": "merged | closed | open",
        "embedding_text": "..."         # text that was embedded (for search)
    }
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from core.logger import get_logger
from rag.rag_config import RAGSettings, get_rag_settings

logger = get_logger("rag.history_indexer")


# ── Review history entry schema ────────────────────────────────────────


def _make_entry(
    pr_number: int,
    repo: str,
    title: str,
    diff_summary: str,
    findings: list[dict],
    resolution: str = "open",
    reviewer_comments: Optional[list[str]] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """Construct a well-formed review history entry.

    Args:
        pr_number: GitHub/GitLab PR number.
        repo: Repository identifier in ``'owner/repo'`` format.
        title: PR title.
        diff_summary: Short human-readable summary of the diff.
        findings: List of finding dicts (from PipelineResult or SandboxResult).
        resolution: ``'merged'``, ``'closed'``, or ``'open'``.
        reviewer_comments: Optional list of human reviewer comment strings.
        metadata: Additional key-value context.

    Returns:
        Dict with all required fields for JSONL storage.
    """
    # Build the embedding text from the most searchable parts
    embedding_text = _build_embedding_text(title, diff_summary, findings)

    return {
        "pr_number": pr_number,
        "repo": repo,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "diff_summary": diff_summary,
        "findings": findings,
        "reviewer_comments": reviewer_comments or [],
        "resolution": resolution,
        "embedding_text": embedding_text,
        "metadata": metadata or {},
    }


def _build_embedding_text(title: str, diff_summary: str, findings: list[dict]) -> str:
    """Build a condensed string for embedding the review entry.

    Combines title, summary, and top finding messages to represent the
    review semantically.
    """
    parts = [f"PR: {title}", f"Summary: {diff_summary}"]
    for f in findings[:10]:  # top 10 findings
        msg = f.get("comment") or f.get("message", "")
        if msg:
            parts.append(f"Finding: {msg[:150]}")
    return "\n".join(parts)


# ── HistoryIndexer class ───────────────────────────────────────────────


class HistoryIndexer:
    """Persistent store of PR review history with semantic search.

    Writes review entries to a JSONL file and maintains an in-memory
    FAISS index for fast semantic retrieval of similar past reviews.

    The FAISS index is rebuilt on load from the JSONL file so it is
    always consistent with the persisted data.

    Example::

        indexer = HistoryIndexer(embedding_model)
        indexer.load()

        # Save a new review
        indexer.add_review(
            pr_number=123,
            repo="owner/repo",
            title="Fix SQL injection in auth module",
            diff_summary="Added parameterized queries",
            findings=[{"severity": "error", "message": "SQL injection risk"}],
        )

        # Find similar past reviews
        similar = indexer.find_similar("SQL injection authentication", k=3)
        for entry in similar:
            print(entry["pr_number"], entry["title"])
    """

    def __init__(
        self,
        embedding_model: Any,
        settings: Optional[RAGSettings] = None,
    ) -> None:
        self._cfg = settings or get_rag_settings()
        self._embeddings = embedding_model
        self._history_path = self._cfg.RAG_HISTORY_PATH
        self._max_entries = self._cfg.RAG_HISTORY_MAX_ENTRIES
        self._entries: list[dict] = []
        self._vectorstore = None

    # ── Public API ─────────────────────────────────────────────────────

    def load(self) -> int:
        """Load entries from the JSONL file and rebuild the search index.

        Returns:
            Number of entries loaded.
        """
        self._entries = self._read_jsonl()
        if self._entries:
            self._rebuild_index()
        logger.info(
            "HistoryIndexer: loaded %d entries from %s",
            len(self._entries), self._history_path,
        )
        return len(self._entries)

    def add_review(
        self,
        pr_number: int,
        repo: str,
        title: str,
        diff_summary: str,
        findings: list[dict],
        resolution: str = "open",
        reviewer_comments: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Add a new review entry and persist it.

        If the same PR already exists, it is updated in place.

        Args:
            pr_number: PR/MR number.
            repo: Repository identifier.
            title: PR title.
            diff_summary: Short summary of the diff.
            findings: List of finding dicts.
            resolution: 'open' | 'merged' | 'closed'.
            reviewer_comments: Optional human comments.
            metadata: Extra key-value context.

        Returns:
            The saved entry dict.
        """
        entry = _make_entry(
            pr_number=pr_number,
            repo=repo,
            title=title,
            diff_summary=diff_summary,
            findings=findings,
            resolution=resolution,
            reviewer_comments=reviewer_comments,
            metadata=metadata,
        )

        # Remove existing entry for same PR + repo
        self._entries = [
            e for e in self._entries
            if not (e.get("pr_number") == pr_number and e.get("repo") == repo)
        ]
        self._entries.append(entry)

        # Enforce max entries (FIFO eviction)
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]

        self._persist()
        self._rebuild_index()

        logger.info(
            "HistoryIndexer: saved review PR#%d (%s) — total=%d",
            pr_number, repo, len(self._entries),
        )
        return entry

    def update_resolution(self, pr_number: int, repo: str, resolution: str) -> bool:
        """Update the resolution status of an existing review entry.

        Args:
            pr_number: PR number to update.
            repo: Repository identifier.
            resolution: New resolution status.

        Returns:
            True if the entry was found and updated.
        """
        for entry in self._entries:
            if entry.get("pr_number") == pr_number and entry.get("repo") == repo:
                entry["resolution"] = resolution
                self._persist()
                return True
        return False

    def find_similar(self, query: str, k: int = 3) -> list[dict]:
        """Find past review entries semantically similar to the query.

        Falls back to most-recent-first ordering if the vector index is
        not available.

        Args:
            query: Natural language or code snippet to search for.
            k: Number of similar entries to return.

        Returns:
            List of review entry dicts, most relevant first.
        """
        if self._vectorstore is None:
            logger.debug("HistoryIndexer: no index available — returning recent entries")
            return self._entries[-k:][::-1]

        try:
            results = self._vectorstore.similarity_search(query, k=k)
            entries: list[dict] = []
            for doc in results:
                pr_num = doc.metadata.get("pr_number")
                repo = doc.metadata.get("repo")
                for entry in self._entries:
                    if entry.get("pr_number") == pr_num and entry.get("repo") == repo:
                        entries.append(entry)
                        break
            return entries
        except Exception as exc:
            logger.error("HistoryIndexer search error: %s", exc)
            return self._entries[-k:][::-1]

    def format_for_prompt(self, query: str, k: int = 3) -> str:
        """Return past review context formatted for LLM prompt injection.

        Args:
            query: Query to find relevant history.
            k: Number of past reviews to include.

        Returns:
            Multi-line string describing past relevant reviews.
        """
        similar = self.find_similar(query, k=k)
        if not similar:
            return ""

        lines = ["## Relevant Past Reviews\n"]
        for entry in similar:
            lines.append(
                f"**PR #{entry['pr_number']}** ({entry['repo']}) — "
                f"{entry['title']} [{entry['resolution']}]"
            )
            lines.append(f"Summary: {entry['diff_summary']}")
            top_findings = entry.get("findings", [])[:3]
            for f in top_findings:
                msg = f.get("comment") or f.get("message", "")
                sev = f.get("severity", "")
                if msg:
                    lines.append(f"  - [{sev}] {msg[:150]}")
            lines.append("")

        return "\n".join(lines)

    @property
    def entry_count(self) -> int:
        """Return the number of stored review entries."""
        return len(self._entries)

    # ── Private helpers ────────────────────────────────────────────────

    def _read_jsonl(self) -> list[dict]:
        """Read all entries from the JSONL file."""
        if not os.path.exists(self._history_path):
            return []
        entries: list[dict] = []
        try:
            with open(self._history_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except OSError as exc:
            logger.error("HistoryIndexer: could not read %s: %s", self._history_path, exc)
        return entries

    def _persist(self) -> None:
        """Write all entries to the JSONL file."""
        os.makedirs(os.path.dirname(self._history_path) or ".", exist_ok=True)
        try:
            with open(self._history_path, "w", encoding="utf-8") as f:
                for entry in self._entries:
                    f.write(json.dumps(entry, default=str) + "\n")
        except OSError as exc:
            logger.error("HistoryIndexer: could not write %s: %s", self._history_path, exc)

    def _rebuild_index(self) -> None:
        """Rebuild the in-memory FAISS search index from current entries."""
        if not self._entries:
            self._vectorstore = None
            return

        try:
            from langchain_community.vectorstores import FAISS
            from langchain.schema import Document

            docs = [
                Document(
                    page_content=entry.get("embedding_text", entry.get("title", "")),
                    metadata={
                        "pr_number": entry.get("pr_number", 0),
                        "repo": entry.get("repo", ""),
                        "resolution": entry.get("resolution", "open"),
                    },
                )
                for entry in self._entries
                if entry.get("embedding_text") or entry.get("title")
            ]

            if docs:
                self._vectorstore = FAISS.from_documents(docs, self._embeddings)
                logger.debug(
                    "HistoryIndexer: rebuilt FAISS index with %d entries", len(docs)
                )
        except Exception as exc:
            logger.warning("HistoryIndexer: could not build FAISS index: %s", exc)
            self._vectorstore = None
