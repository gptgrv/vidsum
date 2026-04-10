"""YouTube caption fast path.

When YouTube exposes captions, fetching text is much faster than downloading
audio and running Whisper. If captions are missing or malformed, callers fall
back to the normal audio transcription path.
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass

import yt_dlp

from .config import cache_dir_for
from .download import slugify
from .transcribe import _load_cached
from .types import Transcript, TranscriptSegment

YOUTUBE_URL_RE = re.compile(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/", re.I)
CAPTION_LANGS = ("en-orig", "en")


@dataclass
class CaptionTranscriptResult:
    title: str
    slug: str
    duration_seconds: float
    transcript: Transcript
    source: str


def fetch_youtube_caption_transcript(
    url: str,
    *,
    fresh: bool = False,
) -> CaptionTranscriptResult | None:
    if not YOUTUBE_URL_RE.match(url):
        return None

    info = _probe_youtube(url)
    title = info.get("title") or info.get("id") or "untitled"
    slug = slugify(title)
    duration_seconds = float(info.get("duration") or 0.0)

    cache_path = cache_dir_for(slug) / "transcript.json"
    if cache_path.exists() and not fresh:
        return CaptionTranscriptResult(
            title=title,
            slug=slug,
            duration_seconds=duration_seconds,
            transcript=_load_cached(cache_path),
            source="cache",
        )

    caption = _select_caption(info)
    if caption is None:
        return None

    try:
        payload = _fetch_text(caption["url"])
        transcript = _parse_caption_payload(
            payload,
            ext=caption["ext"],
            language=caption["language"],
            duration_seconds=duration_seconds,
        )
    except Exception:
        return None

    if not transcript.segments:
        return None

    _save_caption_transcript(cache_path, transcript, source=caption["source"])
    return CaptionTranscriptResult(
        title=title,
        slug=slug,
        duration_seconds=duration_seconds,
        transcript=transcript,
        source=caption["source"],
    )


def _probe_youtube(url: str) -> dict:
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _select_caption(info: dict) -> dict | None:
    for source_key, source_name in (
        ("subtitles", "youtube-subtitles"),
        ("automatic_captions", "youtube-auto-captions"),
    ):
        captions = info.get(source_key) or {}
        for language in CAPTION_LANGS:
            for ext in ("json3", "vtt"):
                for caption in captions.get(language) or []:
                    if caption.get("ext") == ext and caption.get("url"):
                        return {
                            "url": caption["url"],
                            "ext": ext,
                            "language": "en",
                            "source": source_name,
                        }
    return None


def _fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8")


def _parse_caption_payload(
    payload: str,
    *,
    ext: str,
    language: str,
    duration_seconds: float,
) -> Transcript:
    if ext == "json3":
        return _parse_json3_caption(payload, language=language, duration_seconds=duration_seconds)
    if ext == "vtt":
        return _parse_vtt_caption(payload, language=language, duration_seconds=duration_seconds)
    raise ValueError(f"unsupported caption format: {ext}")


def _parse_json3_caption(
    payload: str,
    *,
    language: str,
    duration_seconds: float,
) -> Transcript:
    obj = json.loads(payload)
    segments: list[TranscriptSegment] = []
    for event in obj.get("events") or []:
        text = "".join(seg.get("utf8", "") for seg in event.get("segs") or [])
        text = " ".join(text.split())
        if not text:
            continue
        start = float(event.get("tStartMs") or 0) / 1000
        duration = float(event.get("dDurationMs") or 0) / 1000
        end = start + duration if duration > 0 else start
        segments.append(TranscriptSegment(start=start, end=end, text=text))

    duration = duration_seconds or (segments[-1].end if segments else 0.0)
    return Transcript(language=language, duration_seconds=duration, segments=segments)


def _parse_vtt_caption(
    payload: str,
    *,
    language: str,
    duration_seconds: float,
) -> Transcript:
    segments: list[TranscriptSegment] = []
    blocks = re.split(r"\n\s*\n", payload)
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines or lines[0].upper().startswith("WEBVTT"):
            continue
        time_idx = next((i for i, line in enumerate(lines) if " --> " in line), None)
        if time_idx is None:
            continue
        start_text, end_text = lines[time_idx].split(" --> ", 1)
        text = " ".join(_strip_vtt_tags(line) for line in lines[time_idx + 1 :])
        text = " ".join(text.split())
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                start=_parse_vtt_time(start_text),
                end=_parse_vtt_time(end_text.split()[0]),
                text=text,
            )
        )

    duration = duration_seconds or (segments[-1].end if segments else 0.0)
    return Transcript(language=language, duration_seconds=duration, segments=segments)


def _parse_vtt_time(text: str) -> float:
    parts = text.replace(",", ".").split(":")
    seconds = float(parts[-1])
    minutes = int(parts[-2]) if len(parts) >= 2 else 0
    hours = int(parts[-3]) if len(parts) >= 3 else 0
    return hours * 3600 + minutes * 60 + seconds


def _strip_vtt_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    return text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")


def _save_caption_transcript(path, transcript: Transcript, *, source: str) -> None:
    obj = {
        "source": source,
        "language": transcript.language,
        "duration_seconds": transcript.duration_seconds,
        "segments": [
            {"start": s.start, "end": s.end, "text": s.text} for s in transcript.segments
        ],
    }
    path.write_text(json.dumps(obj, indent=2))
