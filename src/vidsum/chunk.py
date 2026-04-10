"""Semantic, segment-aware chunking.

Walks Whisper segments in order and accumulates them into chunks until a token
budget is hit. Never splits mid-segment, so per-chunk timestamp ranges are clean.
"""

from __future__ import annotations

from functools import lru_cache

from .config import CHUNK_TOKEN_BUDGET
from .types import Chunk, Transcript


@lru_cache(maxsize=1)
def _encoder():
    import tiktoken
    # cl100k is fine for rough counting; we don't need exact for the target LLMs.
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoder().encode(text))


def chunk_transcript(
    transcript: Transcript, *, budget: int = CHUNK_TOKEN_BUDGET
) -> list[Chunk]:
    chunks: list[Chunk] = []
    buf_text: list[str] = []
    buf_tokens = 0
    buf_start: float | None = None
    buf_end: float = 0.0
    idx = 0

    for seg in transcript.segments:
        seg_tokens = count_tokens(seg.text)

        # If a single segment is huge (rare but possible), let it form its own chunk.
        if seg_tokens >= budget and not buf_text:
            chunks.append(
                Chunk(
                    index=idx,
                    start=seg.start,
                    end=seg.end,
                    text=seg.text.strip(),
                    token_estimate=seg_tokens,
                )
            )
            idx += 1
            continue

        if buf_tokens + seg_tokens > budget and buf_text:
            chunks.append(
                Chunk(
                    index=idx,
                    start=buf_start or 0.0,
                    end=buf_end,
                    text=" ".join(buf_text).strip(),
                    token_estimate=buf_tokens,
                )
            )
            idx += 1
            buf_text = []
            buf_tokens = 0
            buf_start = None

        if buf_start is None:
            buf_start = seg.start
        buf_text.append(seg.text.strip())
        buf_tokens += seg_tokens
        buf_end = seg.end

    if buf_text:
        chunks.append(
            Chunk(
                index=idx,
                start=buf_start or 0.0,
                end=buf_end,
                text=" ".join(buf_text).strip(),
                token_estimate=buf_tokens,
            )
        )

    return chunks


def format_timestamp(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"
