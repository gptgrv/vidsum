"""Shared dataclasses passed between pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DownloadResult:
    url: str
    slug: str
    title: str
    duration_seconds: float
    audio_path: Path


@dataclass
class TranscriptSegment:
    start: float          # seconds
    end: float            # seconds
    text: str


@dataclass
class Transcript:
    language: str
    duration_seconds: float
    segments: list[TranscriptSegment]

    @property
    def full_text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments)


@dataclass
class Chunk:
    index: int
    start: float          # seconds
    end: float            # seconds
    text: str
    token_estimate: int


@dataclass
class Summary:
    """Structured summary. Same shape across local + cloud, single-pass + refine."""
    tldr: str                             # 2-4 paragraphs of prose
    body: str                             # free-form markdown the model authored itself
    actionable_takeaways: list[str]       # may be []; only if the source genuinely surfaces any


@dataclass
class StageTiming:
    name: str
    seconds: float
    extra: dict = field(default_factory=dict)


@dataclass
class RunRecord:
    run_id: str
    url: str
    slug: str
    title: str
    duration_seconds: float
    backend: str                          # "local" or "cloud"
    whisper_model: str
    llm_model: str
    stages: list[StageTiming]
    total_seconds: float
    estimated_cost_usd: float
    timestamp: str
