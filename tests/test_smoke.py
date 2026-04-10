"""End-to-end smoke test.

Skipped by default — runs only when VIDSUM_SMOKE_URL is set, since it requires
network access, ollama running, and several minutes of compute. CI does not run it.
"""

from __future__ import annotations

import os

import pytest

from vidsum.pipeline import run_pipeline


@pytest.mark.skipif(
    not os.environ.get("VIDSUM_SMOKE_URL"),
    reason="set VIDSUM_SMOKE_URL to a short (~5 min) public video to enable",
)
def test_end_to_end_local() -> None:
    url = os.environ["VIDSUM_SMOKE_URL"]
    result = run_pipeline(url, backend_kind="local", quiet=True)

    assert result.summary.tldr, "TL;DR is empty"
    assert result.summary.body, "body is empty"
    assert result.title
    assert result.duration_seconds > 0
    summarize_stage = next(s for s in result.run_record.stages if s.name == "summarize")
    assert summarize_stage.extra.get("n_calls", 0) >= 1


def test_chunker_handles_empty_transcript() -> None:
    from vidsum.chunk import chunk_transcript
    from vidsum.types import Transcript

    chunks = chunk_transcript(Transcript(language="en", duration_seconds=0, segments=[]))
    assert chunks == []


def test_chunker_respects_budget() -> None:
    from vidsum.chunk import chunk_transcript
    from vidsum.types import Transcript, TranscriptSegment

    segs = [
        TranscriptSegment(start=i * 5, end=(i + 1) * 5, text=("hello world " * 50))
        for i in range(40)
    ]
    transcript = Transcript(language="en", duration_seconds=200, segments=segs)
    chunks = chunk_transcript(transcript, budget=500)
    assert len(chunks) >= 2
    for c in chunks:
        # Allow some slack since we never split mid-segment.
        assert c.token_estimate <= 500 + 200
