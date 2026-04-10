"""Paths and constants. Single source of truth for where things live."""

from __future__ import annotations

import os
from pathlib import Path

# Cache lives outside the repo. Audio + transcripts + intermediates go here.
CACHE_ROOT = Path(os.environ.get("VIDSUM_CACHE", Path.home() / ".cache" / "vidsum"))

# Output dir for final summaries. Defaults to cwd/summaries.
def output_dir() -> Path:
    return Path(os.environ.get("VIDSUM_OUT", Path.cwd() / "summaries"))

# Run log (timing / token / cost records). Defaults to cwd/runs.jsonl.
def runs_log_path() -> Path:
    return Path(os.environ.get("VIDSUM_RUNS_LOG", Path.cwd() / "runs.jsonl"))

# Optional external profile sources.
OPENCLAW_WORKSPACE = Path(
    os.environ.get("VIDSUM_OPENCLAW_WORKSPACE", Path.home() / ".openclaw" / "workspace")
)
# Only files that describe the user. Avoid agent persona files.
OPENCLAW_PROFILE_FILES = ["USER.md", "MEMORY.md"]

# Claude project memory (optional supplemental source).
CLAUDE_MEMORY_DIR = Path(
    os.environ.get(
        "VIDSUM_CLAUDE_MEMORY_DIR",
        Path.home() / ".claude" / "projects" / "-Users-gaurav-projects-vidsum" / "memory",
    )
)

# Local profile source.
def local_profile_path() -> Path:
    return Path(os.environ.get("VIDSUM_PROFILE_PATH", Path.cwd() / "profile.md"))

# Whisper defaults.
DEFAULT_WHISPER_MODEL = "distil-large-v3"

# LLM defaults.
DEFAULT_LOCAL_MODEL = "qwen2.5:7b"
DEFAULT_CLOUD_MODEL = "claude-sonnet-4-6"
DEFAULT_OPENAI_MODEL = "gpt-4o"

# Single-pass vs refine-chain dispatch.
#
# If the full transcript fits under this many input tokens, we skip the lossy
# refine chain entirely and feed the whole transcript to the model in one shot.
# This is dramatically higher quality and faster for short/medium videos.
# At ~150 wpm, 12k tokens ≈ 60 minutes of speech.
SINGLE_PASS_TOKEN_THRESHOLD = 12000

# Refine-chain budgets (tokens), used only when the transcript exceeds the
# single-pass threshold above.
CHUNK_TOKEN_BUDGET = 6000
ROLLING_SUMMARY_BUDGET = 6000
ROLLING_SUMMARY_MAX_TOKENS = 6144
REFINE_FINAL_MAX_TOKENS = 12288

# Cost estimation (USD per million tokens) for runs.jsonl.
# Sonnet 4.6 reference pricing.
CLOUD_INPUT_COST_PER_MTOK = 3.0
CLOUD_OUTPUT_COST_PER_MTOK = 15.0


def cache_dir_for(slug: str) -> Path:
    d = CACHE_ROOT / slug
    d.mkdir(parents=True, exist_ok=True)
    return d
