"""Pipeline orchestrator. Wires download → transcribe → summarise → output."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from .backends import make_backend
from .captions import fetch_youtube_caption_transcript
from .chunk import chunk_transcript, count_tokens, format_timestamp
from .config import (
    CLOUD_INPUT_COST_PER_MTOK,
    CLOUD_OUTPUT_COST_PER_MTOK,
    DEFAULT_WHISPER_MODEL,
    SINGLE_PASS_TOKEN_THRESHOLD,
)
from .download import download_audio
from .observability import make_run_id, now_iso, stage
from .profile import load_profile
from .refine import summarize_refine_chain, summarize_single_pass
from .transcribe import transcribe
from .types import RunRecord, StageTiming, Summary


@dataclass
class PipelineResult:
    summary: Summary
    title: str
    url: str
    slug: str
    duration_seconds: float
    backend_name: str
    run_record: RunRecord


def run_pipeline(
    url: str,
    *,
    backend_kind: str = "local",
    model: str | None = None,
    whisper_model: str = DEFAULT_WHISPER_MODEL,
    fresh: bool = False,
    quiet: bool = False,
) -> PipelineResult:
    timings: list[StageTiming] = []
    run_id = make_run_id()

    with stage("captions", timings, quiet=quiet) as extra:
        caption_result = fetch_youtube_caption_transcript(url, fresh=fresh)
        extra["hit"] = caption_result is not None
        if caption_result is not None:
            extra["source"] = caption_result.source
            extra["language"] = caption_result.transcript.language
            extra["duration_s"] = round(caption_result.transcript.duration_seconds, 1)
            extra["segments"] = len(caption_result.transcript.segments)

    if caption_result is not None:
        title = caption_result.title
        slug = caption_result.slug
        transcript = caption_result.transcript
    else:
        with stage("download", timings, quiet=quiet) as extra:
            dl = download_audio(url, fresh=fresh)
            title = dl.title
            slug = dl.slug
            extra["title"] = dl.title
            extra["duration_s"] = round(dl.duration_seconds, 1)

        with stage("transcribe", timings, quiet=quiet) as extra:
            transcript = transcribe(dl, model_name=whisper_model, fresh=fresh, quiet=quiet)
            extra["language"] = transcript.language
            extra["audio_s"] = round(transcript.duration_seconds, 1)
            extra["segments"] = len(transcript.segments)

    backend = make_backend(backend_kind, model=model)

    # Profile is only useful for cloud models. Local 7B models don't have the
    # capacity to meaningfully personalise — the profile just eats context that
    # would be better spent on transcript and response quality.
    profile_text = load_profile() if backend.name == "cloud" else ""

    # Decide path: single-pass for short/medium videos, refine chain for long ones.
    transcript_tokens = count_tokens(transcript.full_text)
    use_single_pass = transcript_tokens <= SINGLE_PASS_TOKEN_THRESHOLD

    if use_single_pass:
        if not quiet:
            print(
                f"[summarize] single-pass path "
                f"({transcript_tokens} tok ≤ {SINGLE_PASS_TOKEN_THRESHOLD} threshold)",
                file=sys.stderr,
                flush=True,
            )
        with stage("summarize", timings, quiet=quiet) as extra:
            summary, stats = summarize_single_pass(
                transcript,
                backend=backend,
                profile=profile_text,
                title=title,
                duration_seconds=transcript.duration_seconds,
                url=url,
                quiet=quiet,
            )
            extra["path"] = "single-pass"
            extra["transcript_tokens"] = transcript_tokens
            extra["n_calls"] = stats["n_calls"]
            extra["input_tokens"] = stats["input_tokens"]
            extra["output_tokens"] = stats["output_tokens"]
    else:
        if not quiet:
            print(
                f"[summarize] refine-chain path "
                f"({transcript_tokens} tok > {SINGLE_PASS_TOKEN_THRESHOLD} threshold)",
                file=sys.stderr,
                flush=True,
            )
        with stage("chunk", timings, quiet=quiet) as extra:
            chunks = chunk_transcript(transcript)
            extra["n_chunks"] = len(chunks)
        with stage("summarize", timings, quiet=quiet) as extra:
            summary, stats = summarize_refine_chain(
                chunks,
                backend=backend,
                profile=profile_text,
                title=title,
                duration_seconds=transcript.duration_seconds,
                url=url,
                quiet=quiet,
            )
            extra["path"] = "refine-chain"
            extra["n_chunks"] = len(chunks)
            extra["n_calls"] = stats["n_calls"]
            extra["input_tokens"] = stats["input_tokens"]
            extra["output_tokens"] = stats["output_tokens"]

    total = sum(t.seconds for t in timings)
    cost = _estimate_cost(backend.name, stats["input_tokens"], stats["output_tokens"])

    record = RunRecord(
        run_id=run_id,
        url=url,
        slug=slug,
        title=title,
        duration_seconds=transcript.duration_seconds,
        backend=backend.name,
        whisper_model=whisper_model,
        llm_model=backend.model,
        stages=timings,
        total_seconds=total,
        estimated_cost_usd=cost,
        timestamp=now_iso(),
    )

    return PipelineResult(
        summary=summary,
        title=title,
        url=url,
        slug=slug,
        duration_seconds=transcript.duration_seconds,
        backend_name=backend.name,
        run_record=record,
    )


def _estimate_cost(backend_name: str, input_tokens: int, output_tokens: int) -> float:
    if backend_name != "cloud":
        return 0.0
    return (
        input_tokens * CLOUD_INPUT_COST_PER_MTOK / 1_000_000
        + output_tokens * CLOUD_OUTPUT_COST_PER_MTOK / 1_000_000
    )


def duration_str(seconds: float) -> str:
    return format_timestamp(seconds)
