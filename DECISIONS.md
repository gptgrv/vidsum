# Design Decisions

Locked decisions from the initial design interview. This file is the source of truth. When a decision changes, update here and note what changed and why.

## Scope & shape

- **v1 = standalone local CLI.** The primary artifact is a Git-installable command, `vidsum <url>`, that a human or another local model can invoke non-interactively. Agent compatibility still matters, but the repo should stand on its own without platform-specific wrappers.
- **Core as a reusable module.** CLI is a thin wrapper so the later web UI and queue ingestion reuse the same core without refactoring.
- **Automation-friendliness is a day-1 constraint, not a retrofit.** Clean stdout/stderr separation (summary content to stdout or a known path, progress/logs to stderr), meaningful exit codes, a `--json` output mode, no interactive prompts ever, predictable output file paths.
- **Target volume:** ~5 videos/week, long-form (15 min – 3 hr).
- **Hobby-project disposition.** Optimize for "fun to work on" and "evolves as we learn," not for rigor or exhaustive coverage. Loose build order, permission to change direction.
- **Deferred to roadmap:** local web UI, queue/inbox ingestion, speaker diarization, hosted web service, dedicated-hardware scale-out.

## Chunking parameters

- **Boundary strategy:** semantic — accumulate transcript segments until a token budget is hit, never split mid-segment. Preserves per-chunk timestamps through the pipeline.
- **Chunk size budget:** ~6k tokens of content (~25 min speech), ~2k for rolling summary carryover, ~1.5k for system prompt + profile, ~1.5k response headroom → ~11k tokens per pass, well inside safe range.
- **Expected call count:** ~5 chunks for a 2hr video → 5 refine passes + 1 final polish = **6 LLM calls per summary**.

## Project layout

- **Dependency management:** `uv`
- **Layout:** `src/vidsum/` + `pyproject.toml`
- **Linting:** Ruff, nothing else
- **CLI name:** `vidsum`
- **Tests in v1:** a single end-to-end smoke test against a short known video. Nothing more until pain justifies it.

## Stack

- **Language:** Python.
- **Audio download:** `yt-dlp` (handles YouTube, Twitter/X, Vimeo, most platforms, and raw mp4/mp3/podcast URLs uniformly).
- **Transcription:** for YouTube URLs, try English manual/automatic captions first and skip audio entirely when available. Otherwise use `faster-whisper` with `distil-large-v3` as default. ~4–6x faster than `large-v3` with ~1% WER degradation on English — the right fallback tradeoff for English-only content on base M4. `--whisper-model large-v3` is available for max accuracy on important/hard audio.
- **Local LLM:** Qwen 2.5 7B via Ollama (or equivalent). Chosen because 16 GB unified memory caps us at ~7B–14B Q4.
- **Target hardware:** M4 base (not Max), 16 GB unified memory. Memory bandwidth is ~120 GB/s, which makes transcription and inference meaningfully slower than M4 Max. Every design decision about model size, chunking, and caching assumes this constraint — reviewing decisions when/if hardware changes is worthwhile.
- **Cloud LLM:** Claude Sonnet 4.6 (`claude-sonnet-4-6`) as the comparison/escape-hatch backend.

## Summarization strategy

- **No fine-tuning.** Not in v1, probably not ever for this project. Lacks training data, LoRA on 16 GB is miserable, gains are marginal vs. prompting + profile + chunking, and locks us to one model.
- **Quality levers are:** (1) prompts, (2) user profile injection, (3) the dispatch between single-pass and refine chain.
- **Two summarisation paths, dispatched on transcript token count:**
  - **Single-pass** (transcript ≤ 12k tokens, ~60 min of speech): one LLM call sees the full transcript and produces the structured summary directly. This is the preferred path because it is dramatically higher quality — the model sees the original content, not a lossy compressed intermediate. Faster too.
  - **Refine chain** (transcript > 12k tokens): chunk semantically (~6k tokens per chunk), maintain a rolling markdown summary across chunks, then run a final pass that turns the rolling summary into the structured Summary. Used only when the source is too long to fit single-pass.
- **Why the threshold is 12k tokens:** Qwen 2.5 7B's effective context on 16 GB is ~16–32k tokens. Single-pass uses ~14k input + ~4k output, comfortably inside that. Smaller models degrade past their effective context regardless of advertised 131k.
- **Earlier design (deprecated):** the original plan ran refine chain unconditionally. This was removed because for short/medium videos the chain crushed information into a tight rolling summary that the final pass couldn't recover from — outputs were thin and bland. Single-pass fixes this for the common case; refine chain stays as the fallback for genuinely long content.

## Backends & UX

- **Default backend: local Qwen 7B.** Free, private, slow-ish.
- **Cloud is opt-in:** `--cloud` runs Sonnet 4.6 instead of local, `--compare` runs both and writes both outputs for side-by-side calibration.
- **Pipeline is model-agnostic.** Backend swap is a config choice, not a code change. "No cloud fallback" = don't configure one, not absence of the capability.

## Output

- **Structure:**
  1. TL;DR — 2–4 paragraphs of substantive prose. Captures the actual argument, not just the topic.
  2. Body — free-form markdown the model structures itself with `##` and `###` headings. Length scales with source duration. The model decides organisation based on what the source contains; we do not impose a fixed schema.
  3. Actionable takeaways — conditional; only when the video genuinely surfaces any. Never forced or padded.
- **What was tried and removed:** an earlier version had Key Claims, a Timestamp Index, and a "Why this matters to you" section. All three were removed because (a) the model wrote thinly when boxed into a fixed structure, (b) timestamps from a 7B were unreliable and required defensive validation, and (c) the personalisation section invited forced metaphors when the profile had no genuine angle. The body absorbs all of this — personalisation lives in emphasis and vocabulary, not in a labelled section.
- **Personalisation is subtle, not explicit.** Profile shapes emphasis, vocabulary, and what gets elaborated vs. elided. The model is forbidden from name-dropping, "as someone who..." phrasings, and forced connections between unrelated profile facts and video content. If the profile has no relevant angle, the body reads as a normal high-quality summary with no personalisation.

## Storage & caching

- **Intermediates (audio, raw transcripts, chunk summaries):** `~/.cache/vidsum/<slug>/`. Regeneratable, large, not precious.
- **Final summaries:** `./summaries/` (user-owned, in or near the invocation directory). Small, precious, greppable.
- **Idempotency:** re-running `summarize <same-url>` reuses the cached transcript and regenerates the summary. Never re-fetches captions or re-transcribes unless `--fresh` is passed. Iterating on prompts does not re-pay the transcription cost.
- **YouTube caption fast path:** for YouTube URLs, try English manual or automatic captions first (`json3`, then `vtt`). If available, save them as `transcript.json` and skip audio download + Whisper entirely. If captions are missing or malformed, fall back to the normal audio path.
- **Never commit audio or transcripts to git.** `.gitignore` covers the cache dir and default summaries dir.

## Profile / personalization source

- **Primary source: local `profile.md`.** Lives next to the invocation context by default, or can be overridden with `VIDSUM_PROFILE_PATH`. This is the portable setup path that works from a plain Git checkout.
- **Optional supplemental source: OpenClaw's `USER.md` et al.**, read live when present from `/Users/gaurav/.openclaw/workspace/`:
  - `USER.md` — main profile
  - `MEMORY.md` — supplementary user context
  - Agent persona files are intentionally excluded.
- **Optional supplemental source:** Claude's project memory at `/Users/gaurav/.claude/projects/-Users-gaurav-projects-vidsum/memory/` when available.
- **Read live, never cached.** Zero drift. External workspace context should help when present, but the CLI should remain fully usable without it.
- **Future:** grow profile from summarization history (which videos were chosen, marked useful, ignored). Mechanism TBD — deferred until there's enough real history to learn from.

## Observability

- **Per-stage timing instrumentation from day 1.** Stages: download, transcribe, chunk, each refine step, final pass. Timings persisted to a `runs.jsonl` log so we can (a) see drift over time, (b) spot regressions when tweaking prompts/models, (c) have a concrete feedback loop for quality and performance improvements.

## Explicitly rejected or deferred

- **Fine-tuning** — rejected (see above).
- **Speaker diarization** — deferred to roadmap. Doubles pipeline complexity for a feature that only helps multi-speaker content.
- **Hosted public service** — deferred. Legal/ToS, auth, abuse, cost model all unresolved.
