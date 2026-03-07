"""
Review State Store — tracks last-reviewed SHA, debounce, and locks per PR.

Uses Redis as primary store (with JSON file fallback).
"""

import json
import time
import os
from pathlib import Path
from core.config import get_settings
from core.logger import get_logger

logger = get_logger("core.review_state")

STATE_FILE = Path("data/review_state.json")
BOT_MARKER = "<!-- devassist-ai -->"


_redis_client = None
_redis_checked = False


def _get_redis():
    """Try to get a Redis connection. Returns None if unavailable. Cached at module level."""
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True
    try:
        import redis
        settings = get_settings()
        r = redis.from_url(settings.REDIS_URL, decode_responses=True, socket_timeout=1, socket_connect_timeout=1)
        r.ping()
        _redis_client = r
        logger.info("Redis connected successfully")
    except Exception:
        logger.warning("Redis unavailable — using JSON file fallback for all state operations")
        _redis_client = None
    return _redis_client


def _load_json_state() -> dict:
    """Load the JSON fallback state file."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save_json_state(state: dict):
    """Save state to JSON fallback file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ─── Last Reviewed SHA ────────────────────────────────────────────────────────

def get_last_reviewed_sha(pr_number: int) -> str | None:
    """Get the last reviewed commit SHA for a PR."""
    r = _get_redis()
    if r:
        return r.get(f"devassist:pr:{pr_number}:last_sha")

    state = _load_json_state()
    pr_state = state.get(str(pr_number), {})
    return pr_state.get("last_sha")


def save_reviewed_sha(pr_number: int, sha: str):
    """Save the last reviewed commit SHA for a PR."""
    r = _get_redis()
    if r:
        r.set(f"devassist:pr:{pr_number}:last_sha", sha)
        r.set(f"devassist:pr:{pr_number}:last_review_time", str(time.time()))
        logger.info(f"Saved reviewed SHA for PR #{pr_number}: {sha[:8]}")
        return

    state = _load_json_state()
    state.setdefault(str(pr_number), {})
    state[str(pr_number)]["last_sha"] = sha
    state[str(pr_number)]["last_review_time"] = time.time()
    _save_json_state(state)
    logger.info(f"Saved reviewed SHA for PR #{pr_number}: {sha[:8]} (JSON fallback)")


# ─── Debounce ─────────────────────────────────────────────────────────────────

def should_debounce(pr_number: int) -> bool:
    """Check if a PR was reviewed within the debounce window."""
    settings = get_settings()
    debounce = settings.REVIEW_DEBOUNCE_SECONDS

    r = _get_redis()
    if r:
        last_time = r.get(f"devassist:pr:{pr_number}:last_review_time")
        if last_time and (time.time() - float(last_time)) < debounce:
            logger.info(f"PR #{pr_number} debounced (reviewed {time.time() - float(last_time):.0f}s ago)")
            return True
        return False

    state = _load_json_state()
    pr_state = state.get(str(pr_number), {})
    last_time = pr_state.get("last_review_time")
    if last_time and (time.time() - float(last_time)) < debounce:
        return True
    return False


# ─── Review Lock ──────────────────────────────────────────────────────────────

def acquire_review_lock(pr_number: int, ttl: int = 300) -> bool:
    """
    Acquire a lock for reviewing a PR. Prevents concurrent reviews.
    Returns True if lock acquired, False if already locked.
    TTL ensures locks auto-expire after 5 minutes (in case of crashes).
    """
    r = _get_redis()
    if r:
        lock_key = f"devassist:pr:{pr_number}:lock"
        acquired = r.set(lock_key, "1", nx=True, ex=ttl)
        if acquired:
            logger.info(f"Lock acquired for PR #{pr_number}")
        else:
            logger.info(f"PR #{pr_number} is already locked (review in progress)")
        return bool(acquired)

    # JSON fallback — simple file-based lock (not truly concurrent-safe)
    state = _load_json_state()
    pr_state = state.get(str(pr_number), {})
    lock_time = pr_state.get("lock_time")
    if lock_time and (time.time() - float(lock_time)) < ttl:
        return False  # Still locked
    state.setdefault(str(pr_number), {})
    state[str(pr_number)]["lock_time"] = time.time()
    _save_json_state(state)
    return True


def release_review_lock(pr_number: int):
    """Release the review lock for a PR."""
    r = _get_redis()
    if r:
        r.delete(f"devassist:pr:{pr_number}:lock")
        logger.info(f"Lock released for PR #{pr_number}")
        return

    state = _load_json_state()
    pr_state = state.get(str(pr_number), {})
    pr_state.pop("lock_time", None)
    _save_json_state(state)


# ─── Error Backoff ────────────────────────────────────────────────────────────

def record_failure(pr_number: int):
    """Record a review failure for exponential backoff."""
    r = _get_redis()
    if r:
        key = f"devassist:pr:{pr_number}:failures"
        failures = r.incr(key)
        r.expire(key, 3600)  # Reset after 1 hour
        r.set(f"devassist:pr:{pr_number}:last_failure", str(time.time()))
        return

    state = _load_json_state()
    state.setdefault(str(pr_number), {})
    state[str(pr_number)]["failures"] = state[str(pr_number)].get("failures", 0) + 1
    state[str(pr_number)]["last_failure"] = time.time()
    _save_json_state(state)


def get_backoff_seconds(pr_number: int) -> int:
    """
    Get the backoff delay for a PR based on failure count.
    0 failures → 0s, 1 → 120s, 2 → 300s, 3+ → 900s
    """
    backoff_table = [0, 120, 300, 900]

    r = _get_redis()
    if r:
        failures = int(r.get(f"devassist:pr:{pr_number}:failures") or 0)
        last_failure = float(r.get(f"devassist:pr:{pr_number}:last_failure") or 0)
    else:
        state = _load_json_state()
        pr_state = state.get(str(pr_number), {})
        failures = pr_state.get("failures", 0)
        last_failure = pr_state.get("last_failure", 0)

    if failures == 0:
        return 0

    backoff = backoff_table[min(failures, len(backoff_table) - 1)]
    elapsed = time.time() - last_failure
    remaining = max(0, backoff - int(elapsed))
    return remaining


def clear_failures(pr_number: int):
    """Clear failure counter after a successful review."""
    r = _get_redis()
    if r:
        r.delete(f"devassist:pr:{pr_number}:failures")
        r.delete(f"devassist:pr:{pr_number}:last_failure")
        return

    state = _load_json_state()
    pr_state = state.get(str(pr_number), {})
    pr_state.pop("failures", None)
    pr_state.pop("last_failure", None)
    _save_json_state(state)
