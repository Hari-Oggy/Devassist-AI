"""Prompt registry — loads prompts from external text files."""

import os
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    """
    Load a prompt template by name.
    
    Args:
        name: Prompt file name without extension (e.g. 'review_prompt')
    
    Returns:
        The prompt text content.
    
    Raises:
        FileNotFoundError if the prompt file does not exist.
    """
    path = PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()
