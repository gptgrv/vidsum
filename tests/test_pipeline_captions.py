from __future__ import annotations

from vidsum.captions import CaptionTranscriptResult
from vidsum.types import Summary, Transcript, TranscriptSegment


def test_pipeline_uses_caption_transcript_without_audio(monkeypatch) -> None:
    from vidsum import pipeline

    transcript = Transcript(
        language="en",
        duration_seconds=30,
        segments=[TranscriptSegment(start=0, end=30, text="caption transcript")],
    )
    caption_result = CaptionTranscriptResult(
        title="Caption Video",
        slug="caption-video",
        duration_seconds=30,
        transcript=transcript,
        source="youtube-auto-captions",
    )

    class FakeBackend:
        name = "local"
        model = "fake"

    def fail_audio(*args, **kwargs):
        raise AssertionError("audio path should not run when captions are available")

    monkeypatch.setattr(
        pipeline,
        "fetch_youtube_caption_transcript",
        lambda url, *, fresh=False: caption_result,
    )
    monkeypatch.setattr(pipeline, "download_audio", fail_audio)
    monkeypatch.setattr(pipeline, "transcribe", fail_audio)
    monkeypatch.setattr(pipeline, "load_profile", lambda: "")
    monkeypatch.setattr(pipeline, "make_backend", lambda *args, **kwargs: FakeBackend())
    monkeypatch.setattr(
        pipeline,
        "summarize_single_pass",
        lambda *args, **kwargs: (
            Summary(tldr="ok", body="## Body", actionable_takeaways=[]),
            {"input_tokens": 1, "output_tokens": 1, "n_calls": 1},
        ),
    )

    result = pipeline.run_pipeline("https://www.youtube.com/watch?v=test", quiet=True)

    assert result.title == "Caption Video"
    assert result.slug == "caption-video"
    assert [stage.name for stage in result.run_record.stages] == ["captions", "summarize"]
    assert result.run_record.stages[0].extra["source"] == "youtube-auto-captions"
