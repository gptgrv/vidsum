"""Profile loader.

Reads live every run, never cached. Sources, in order:
  1. Local profile.md (default source)
  2. Optional OpenClaw workspace files (USER.md, MEMORY.md)
  3. Optional Claude project memory

The output is a single text blob to be injected into prompts. Subtle, not in-your-face.
"""

from __future__ import annotations

from .config import (
    CLAUDE_MEMORY_DIR,
    OPENCLAW_PROFILE_FILES,
    OPENCLAW_WORKSPACE,
    local_profile_path,
)


def load_profile() -> str:
    parts: list[str] = []

    # 1. Local profile
    local = _load_local_override()
    if local:
        parts.append("=== Local summarisation preferences ===\n" + local)

    # 2. Optional OpenClaw workspace
    openclaw = _load_openclaw()
    if openclaw:
        parts.append("=== From OpenClaw workspace ===\n" + openclaw)

    # 3. Optional Claude memory
    claude = _load_claude_memory()
    if claude:
        parts.append("=== From Claude project memory ===\n" + claude)

    if not parts:
        return ""
    return "\n\n".join(parts).strip()


def _load_openclaw() -> str:
    if not OPENCLAW_WORKSPACE.exists():
        return ""
    chunks: list[str] = []
    for name in OPENCLAW_PROFILE_FILES:
        p = OPENCLAW_WORKSPACE / name
        if p.exists():
            try:
                content = p.read_text().strip()
            except OSError:
                continue
            if content:
                chunks.append(f"## {name}\n{content}")
    return "\n\n".join(chunks)


def _load_claude_memory() -> str:
    if not CLAUDE_MEMORY_DIR.exists():
        return ""
    index = CLAUDE_MEMORY_DIR / "MEMORY.md"
    if not index.exists():
        return ""
    chunks: list[str] = []
    try:
        chunks.append(f"## MEMORY.md\n{index.read_text().strip()}")
    except OSError:
        return ""
    # Also include other .md files in the dir (the actual memory bodies).
    for p in sorted(CLAUDE_MEMORY_DIR.glob("*.md")):
        if p.name == "MEMORY.md":
            continue
        try:
            content = p.read_text().strip()
        except OSError:
            continue
        if content:
            chunks.append(f"## {p.name}\n{content}")
    return "\n\n".join(chunks)


def _load_local_override() -> str:
    p = local_profile_path()
    if not p.exists():
        return ""
    try:
        return p.read_text().strip()
    except OSError:
        return ""
