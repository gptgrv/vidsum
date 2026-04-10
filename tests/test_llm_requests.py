from __future__ import annotations

from vidsum.backends import LLMResult
from vidsum.config import REFINE_FINAL_MAX_TOKENS, ROLLING_SUMMARY_MAX_TOKENS
from vidsum.refine import _parse_markdown_summary, summarize_refine_chain, summarize_single_pass
from vidsum.types import Chunk, Transcript, TranscriptSegment


class RecordingBackend:
    name = "test"
    model = "test"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []

    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> LLMResult:
        self.calls.append((system, user, max_tokens))
        if max_tokens == ROLLING_SUMMARY_MAX_TOKENS:
            return LLMResult(
                text="rolling summary with chunk needle",
                input_tokens=10,
                output_tokens=5,
            )
        return LLMResult(
            text="## TL;DR\n\nok\n\n## Body\n\nDetails",
            input_tokens=10,
            output_tokens=5,
        )


def test_single_pass_puts_transcript_in_user_message() -> None:
    backend = RecordingBackend()
    transcript = Transcript(
        language="en",
        duration_seconds=65,
        segments=[TranscriptSegment(start=0, end=65, text="transcript needle")],
    )

    summarize_single_pass(
        transcript,
        backend=backend,
        profile="reader profile",
        title="Test Video",
        duration_seconds=65,
        url="https://example.com/video",
        quiet=True,
    )

    system, user, max_tokens = backend.calls[0]
    assert max_tokens == 8192
    assert "reader profile" in system
    assert "transcript needle" not in system
    assert "transcript needle" in user
    assert "- Title: Test Video" in user
    assert "Write the summary now." in user


def test_refine_final_pass_puts_rolling_summary_in_user_message() -> None:
    backend = RecordingBackend()
    chunks = [
        Chunk(
            index=0,
            start=0,
            end=30,
            text="chunk needle",
            token_estimate=3,
        )
    ]

    summarize_refine_chain(
        chunks,
        backend=backend,
        profile="reader profile",
        title="Long Video",
        duration_seconds=30,
        url="https://example.com/long",
        quiet=True,
    )

    final_system, final_user, max_tokens = backend.calls[1]
    assert max_tokens == REFINE_FINAL_MAX_TOKENS
    assert "rolling summary with chunk needle" not in final_system
    assert "rolling summary with chunk needle" in final_user


def test_local_backend_sets_ollama_context_window(monkeypatch) -> None:
    from vidsum.backends.local import LOCAL_NUM_CTX, LocalBackend

    captured: dict = {}

    class FakeOllama:
        @staticmethod
        def chat(**kwargs):
            captured.update(kwargs)
            return {
                "message": {"content": "ok"},
                "prompt_eval_count": 7,
                "eval_count": 2,
            }

    monkeypatch.setitem(__import__("sys").modules, "ollama", FakeOllama)

    result = LocalBackend("qwen-test").complete("system", "user", max_tokens=123)

    assert result.text == "ok"
    assert captured["model"] == "qwen-test"
    assert captured["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "user"},
    ]
    assert captured["options"]["num_ctx"] == LOCAL_NUM_CTX
    assert captured["options"]["num_predict"] == 123


def test_markdown_parser_extracts_tldr_body_and_takeaways() -> None:
    summary = _parse_markdown_summary(
        """## TL;DR

ok

## Picking Ideas

Details

## Actionable takeaways

- one
- two
"""
    )

    assert summary.tldr == "ok"
    assert "## Picking Ideas" in summary.body
    assert summary.actionable_takeaways == ["one", "two"]


def test_markdown_parser_strips_short_meta_preamble() -> None:
    summary = _parse_markdown_summary(
        """Here's your summary.

## TL;DR

ok

## Body

Details
"""
    )

    assert summary.tldr == "ok"
    assert summary.body == "## Body\n\nDetails"
