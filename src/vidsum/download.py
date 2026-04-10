"""Download stage. Wraps yt-dlp to fetch audio from any supported URL."""

from __future__ import annotations

import re
from pathlib import Path

import yt_dlp

from .config import cache_dir_for
from .types import DownloadResult


def slugify(text: str, max_len: int = 80) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text[:max_len] or "untitled"


def download_audio(url: str, *, fresh: bool = False) -> DownloadResult:
    """Download audio from `url`. Returns metadata + path to the audio file.

    Reuses cached audio if present unless fresh=True.
    """
    # Step 1: probe metadata without downloading so we know the slug.
    probe_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(probe_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    title = info.get("title") or info.get("id") or "untitled"
    duration = float(info.get("duration") or 0.0)
    slug = slugify(title)

    cache = cache_dir_for(slug)
    # Look for any pre-existing audio file in the cache dir.
    existing = _find_existing_audio(cache)
    if existing and not fresh:
        return DownloadResult(
            url=url, slug=slug, title=title, duration_seconds=duration, audio_path=existing
        )

    # Step 2: real download. Prefer m4a/opus to avoid re-encoding.
    out_template = str(cache / "audio.%(ext)s")
    download_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(download_opts) as ydl:
        ydl.download([url])

    audio_path = _find_existing_audio(cache)
    if audio_path is None:
        raise RuntimeError(f"yt-dlp completed but no audio file found in {cache}")

    return DownloadResult(
        url=url, slug=slug, title=title, duration_seconds=duration, audio_path=audio_path
    )


def _find_existing_audio(cache_dir: Path) -> Path | None:
    for ext in ("m4a", "opus", "webm", "mp3", "wav", "mp4", "ogg", "aac"):
        candidates = list(cache_dir.glob(f"audio.{ext}"))
        if candidates:
            return candidates[0]
    return None
