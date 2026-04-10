"""Prompt templates loaded as module data."""

from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).parent


def _load(name: str) -> str:
    return (_DIR / name).read_text()


def summarize_prompt() -> str:
    """Used for both single-pass and the final pass after a refine chain."""
    return _load("summarize.md")


def refine_chunk_prompt() -> str:
    """Used per chunk in the refine chain (long videos only)."""
    return _load("refine_chunk.md")


def expand_prompt() -> str:
    """Used for the second pass — expand the most important sections."""
    return _load("expand.md")


def build_profile_prompt() -> str:
    """Used to build a summarisation profile from LinkedIn profile text."""
    return _load("build_profile.md")
