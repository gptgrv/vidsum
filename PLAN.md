# v1 Implementation Plan

Derived from the design interview. See `DECISIONS.md` for the rationale behind each choice and `ROADMAP.md` for what's deferred.

## What we're building

A **standalone** Python CLI, `vidsum`, that takes a URL (YouTube, Twitter/X, podcast episode, raw mp3/mp4, or any `yt-dlp`-supported platform) and produces a personalized markdown (or JSON) summary. It should be easy to install from Git, usable directly by a person at the terminal, and simple for another local model to call as a subprocess. Default backend is a local Qwen 2.5 7B via Ollama. An opt-in `--cloud` flag routes to Claude Sonnet 4.6, and `--compare` runs both for side-by-side calibration.

## Pipeline

```
URL
 │
 ▼
[1] Try YouTube captions        yt-dlp → transcript.json when English captions exist
 │
 ├── captions unavailable ──▶ Download audio
 │                            yt-dlp → ~/.cache/vidsum/<slug>/audio.{ext}
 │
 ▼
[2] Transcribe fallback         faster-whisper distil-large-v3
 │                              → transcript.json (segments with timestamps)
 │
 ▼
[3] Dispatch on token count
 │
 ├── transcript ≤ 12k tok ──▶ Single-pass summarise
 │                            One LLM call sees the full transcript.
 │                            Higher quality, used for short/medium videos.
 │
 └── transcript > 12k tok ──▶ Refine chain
                              [3a] Semantic chunking (~6k tok per chunk)
                              [3b] For each chunk: refine the rolling
                                   markdown summary with the new content.
                              [3c] Final pass turns rolling summary into
                                   structured Summary.
 │
 ▼
[4] Write summary.md            ./summaries/<slug>.md
 │
 ▼
[5] Append run record           runs.jsonl (timings, model, tokens, cost)
```

## Output format (`summary.md`)

Every summary has:

1. **TL;DR** — 2–4 paragraphs of prose. Substance, not "this video discusses X".
2. **Body** — free-form markdown that the model structures itself with `##` and `###` headings. The model picks the structure based on what the source actually contains. Length scales with source duration (~600 words for a 10-min talk, ~3000 for 60-min, ~5000 for 2hr).
3. **Actionable takeaways** — only if the video genuinely surfaces any; never padded or forced.

Personalisation is invisible: it shapes emphasis and vocabulary inside the body, not as a separate section. There is no name-dropping, no "as someone who...", no forced metaphors between unrelated profile facts and the video content.

## Personalization source

Read live every run. Primary: local `./profile.md` (or `VIDSUM_PROFILE_PATH`) for summarization-specific preferences. Secondary: optional OpenClaw workspace files at `/Users/gaurav/.openclaw/workspace/` — `USER.md` and `MEMORY.md`. Tertiary: optional Claude project memory if present.

## Observability

Every stage emits timing + token counts. Appended to `runs.jsonl`:

```json
{
  "run_id": "...",
  "url": "...",
  "slug": "...",
  "backend": "local" | "cloud",
  "whisper_model": "distil-large-v3",
  "llm_model": "qwen2.5:7b",
  "stages": {
    "download":   {"seconds": ..., "bytes": ...},
    "transcribe": {"seconds": ..., "duration_audio_seconds": ...},
    "chunk":      {"seconds": ..., "n_chunks": ...},
    "refine":     {"seconds": ..., "n_calls": ..., "input_tokens": ..., "output_tokens": ...},
    "polish":     {"seconds": ..., "input_tokens": ..., "output_tokens": ...}
  },
  "total_seconds": ...,
  "estimated_cost_usd": ...,
  "timestamp": "..."
}
```

This is the feedback loop for quality and performance iteration.

## Storage layout

```
~/.cache/vidsum/<slug>/             # regeneratable, large, not precious
    audio.<ext>
    transcript.json
    chunks/
        chunk-001.txt
        ...
    rolling/
        after-001.md
        ...

./summaries/<slug>.md                # small, precious, greppable
./runs.jsonl                         # timing log
./profile.md                         # optional local override
```

## CLI surface

```
vidsum <url>                         # local backend, markdown to stdout
vidsum <url> --cloud                 # Claude Sonnet 4.6 instead
vidsum <url> --compare               # run both, write both outputs
vidsum <url> --fresh                 # force re-download and re-transcribe
vidsum <url> --whisper-model large-v3   # opt in to max-accuracy Whisper
vidsum <url> --keep-audio            # don't delete cached audio after run
vidsum <url> --json                  # machine-readable output for agents
vidsum <url> --quiet                 # suppress progress on stderr
vidsum <url> --out <path>            # write summary to specific path (not stdout)
```

## CLI interface contract

- **stdout:** summary content only (markdown by default, JSON with `--json`). Nothing else.
- **stderr:** human-readable progress, stage timings, warnings, errors.
- **Exit codes:** `0` success, `2` bad URL / unsupported source, `3` download failure, `4` transcription failure, `5` LLM failure, `1` everything else.
- **No interactive prompts, ever.** If something is missing, fail with a clear stderr message.
- **`--json` schema** (stable contract):
  ```json
  {
    "url": "...",
    "slug": "...",
    "title": "...",
    "duration_seconds": ...,
    "backend": "local" | "cloud",
    "summary": {
      "tldr": "2-4 paragraphs of prose",
      "body": "free-form markdown with model-defined headings",
      "actionable_takeaways": ["..."]
    },
    "stages": [ ... timing entries ... ],
  "paths": {"markdown": "./summaries/<slug>.md"}
  }
  ```

## Project structure

```
vidsum/
├── pyproject.toml                   # uv, ruff
├── DECISIONS.md
├── ROADMAP.md
├── PLAN.md                          # this file
├── profile.md                       # optional local profile override
├── summaries/                       # output dir
├── runs.jsonl                       # timing log
├── src/
│   └── vidsum/
│       ├── __init__.py
│       ├── cli.py                   # argparse / click entry point, stdout/stderr discipline
│       ├── pipeline.py              # orchestrates the stages
│       ├── download.py              # yt-dlp wrapper
│       ├── transcribe.py            # faster-whisper wrapper
│       ├── chunk.py                 # semantic chunking on whisper segments
│       ├── refine.py                # refine chain driver
│       ├── backends/
│       │   ├── __init__.py          # BackendProtocol
│       │   ├── local.py             # Ollama / llama.cpp client
│       │   └── cloud.py             # Anthropic client
│       ├── profile.py               # reads local profile + optional external memory sources
│       ├── prompts/                 # markdown prompt templates
│       │   ├── refine_chunk.md
│       │   └── final_polish.md
│       ├── output.py                # markdown + JSON serializers
│       └── observability.py         # timing decorators, runs.jsonl writer
└── tests/
    └── test_smoke.py                # end-to-end on a short known video
```

## Build order

Tracer-bullet style — get an end-to-end crappy version working, then improve each stage.

1. **Scaffold** — `uv init`, `pyproject.toml`, empty modules, CLI entry point, `.gitignore` (cache dir, summaries, audio formats, transcripts).
2. **Stage 1: captions/download** — for YouTube, try English captions first; otherwise use `yt-dlp` to download audio into the cache dir.
3. **Stage 2: transcribe fallback** — `faster-whisper` with `distil-large-v3`, output `transcript.json` with segments when captions are unavailable.
4. **Stage 3: chunk** — segment-aware chunker with ~6k token budget.
5. **Stage 5 (crude): single-call summarize** — skip refine chain at first, just stuff whatever fits into one Qwen call. Validates the LLM plumbing end-to-end on short videos.
6. **Stage 6: output writer** — produce a `summary.md` with the 5-section structure (even if sections are sparse initially).
7. **Cloud backend** — Anthropic client, same interface as local backend. `--cloud` flag works.
8. **Profile loader** — read Claude memory dir, concatenate into prompt context.
9. **Stage 4: real refine chain** — replace the crude single-call summarizer with the real hierarchical refinement.
10. **Observability** — timing decorators on each stage, `runs.jsonl` writer, cost estimation for cloud runs.
11. **`--compare` mode** — run both backends, write both outputs.
12. **`--json` output mode** — structured serializer matching the agent interface contract above.
13. **Smoke test** — pick a short public-domain talk (~10 min), assert pipeline completes and produces all 5 sections.
14. **Dogfood** — run on 5 real videos from your queue, read the outputs, iterate on prompts. This is where most of the real quality work happens.

## Explicitly out of scope for v1

- Speaker diarization
- Fine-tuning
- Non-English auto-translation (non-English summaries in source language are fine — no extra work)
- Podcast RSS feed parsing (direct episode URLs only)
- Web UI, hosting, auth
- Growing `profile.md` automatically from usage history (mechanism TBD, roadmap item)

## Honest expectations

- **Transcription** of a 2hr video on base M4 with `distil-large-v3`: expect ~10–15 min.
- **Local summarization** (6 LLM calls on Qwen 7B): expect ~3–8 min.
- **Total local run** on a 2hr video: ~15–25 min wall clock. Not interactive; fire-and-forget.
- **Cloud summarization** on Sonnet 4.6: expect ~20–60 seconds for the LLM portion. On YouTube videos with captions, audio download/transcription is skipped; otherwise transcription still dominates.
- **Quality:** 7B local output will be "competent" — gets the gist, occasionally misses nuance. Cloud will be notably better on dense/technical content. `--compare` mode exists so you can see this for yourself and decide when to reach for cloud.
