"""Transcription stage. Wraps faster-whisper."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .config import DEFAULT_WHISPER_MODEL, cache_dir_for
from .types import DownloadResult, Transcript, TranscriptSegment

# Silence the "no HF_TOKEN, you'll hit rate limits" warning. We download
# the VAD model exactly once per machine, never enough to hit a limit.
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")


def transcribe(
    download: DownloadResult,
    *,
    model_name: str = DEFAULT_WHISPER_MODEL,
    fresh: bool = False,
    quiet: bool = False,
) -> Transcript:
    """Transcribe audio. Caches the result as transcript.json."""
    cache = cache_dir_for(download.slug)
    cache_path = cache / "transcript.json"

    if cache_path.exists() and not fresh:
        return _load_cached(cache_path)

    # Lazy import — faster-whisper has a heavy import cost we don't want at module load.
    from faster_whisper import WhisperModel

    # Apple Silicon: CPU compute_type=int8 gives a good speed/quality balance.
    # Metal/CoreML support in faster-whisper is patchy; CPU is the safe default.
    model = WhisperModel(model_name, device="cpu", compute_type="int8")

    # Auto-detect language. English is the common case but we transparently handle others.
    segments_iter, info = model.transcribe(
        str(download.audio_path),
        vad_filter=True,
        beam_size=5,
    )

    total_audio = info.duration or download.duration_seconds or 0.0
    segments: list[TranscriptSegment] = []
    last_progress_pct = -1
    for s in segments_iter:
        segments.append(TranscriptSegment(start=s.start, end=s.end, text=s.text))
        if not quiet and total_audio > 0:
            pct = int((s.end / total_audio) * 100)
            # Print every 5% to avoid spamming.
            if pct >= last_progress_pct + 5:
                last_progress_pct = pct - (pct % 5)
                mins_done = int(s.end // 60)
                mins_total = int(total_audio // 60)
                print(
                    f"  transcribe: {last_progress_pct:3d}% "
                    f"({mins_done}/{mins_total} min)",
                    file=sys.stderr,
                    flush=True,
                )

    transcript = Transcript(
        language=info.language,
        duration_seconds=info.duration,
        segments=segments,
    )
    _save(cache_path, transcript)
    return transcript


def _save(path: Path, t: Transcript) -> None:
    obj = {
        "language": t.language,
        "duration_seconds": t.duration_seconds,
        "segments": [{"start": s.start, "end": s.end, "text": s.text} for s in t.segments],
    }
    path.write_text(json.dumps(obj, indent=2))


def _load_cached(path: Path) -> Transcript:
    obj = json.loads(path.read_text())
    return Transcript(
        language=obj["language"],
        duration_seconds=obj["duration_seconds"],
        segments=[
            TranscriptSegment(start=s["start"], end=s["end"], text=s["text"])
            for s in obj["segments"]
        ],
    )
