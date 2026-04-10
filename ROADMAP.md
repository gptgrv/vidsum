# Roadmap

Living document. v1 is a standalone local CLI; everything below is deferred until v1 is solid.

## v1 — Standalone local CLI (in progress)
- `vidsum <url>` command, designed for agents to shell out to
- Clean stdout/stderr discipline, `--json` output mode, no interactive prompts
- Handles YouTube, Twitter/X (best-effort), raw mp4/mp3, direct podcast episode URLs, other yt-dlp-supported platforms
- Audio download via `yt-dlp`
- Local transcription via `faster-whisper` with `distil-large-v3` (base M4 16 GB)
- Local LLM summarization (Qwen 2.5 7B via Ollama) + opt-in cloud (Sonnet 4.6)
- Refine-chain hierarchical summarization
- Personalization from local `profile.md` + optional external memory sources + auto-appended watch history
- Timing instrumentation and `runs.jsonl` log from day 1
- Core logic as an importable module so later interfaces reuse it

## Next — `vidsum init` (setup flow)

Guided first-run experience that works for both humans (interactive) and agents (flags).

### Steps
1. **Choose backend** — local (Ollama) or cloud (Anthropic)
2. **Configure backend** — for cloud: API key + model; for local: check Ollama, pull model
3. **Personalisation (optional)** — LinkedIn URL (scrape public profile), fall back to PDF if LinkedIn blocks the request

### Agent interface (non-interactive)
```
vidsum init --backend cloud --api-key sk-ant-...
vidsum init --backend local --model qwen2.5:7b
vidsum init --linkedin-url https://linkedin.com/in/handle
vidsum init --linkedin-pdf ~/Downloads/Profile.pdf   # fallback
```

### Auto-nudge
If user runs `vidsum <url>` with no backend configured, print a helpful message pointing to `vidsum init` instead of a stack trace.

### `vidsum status`
Print what's configured: backend, model, profile yes/no, watch history count. Useful for agents to check state before acting.

### LinkedIn scraping strategy
- Primary: scrape public LinkedIn URL directly
- If LinkedIn blocks (403/captcha): tell the user, suggest PDF fallback
- PDF path remains supported as `--linkedin-pdf`

## Later

### (b) Local web UI
Runs on `localhost`. Paste URL, get rendered markdown summary. Reuses the v1 core module. Nice for reading long summaries and for eventual public hosting.

### (c) Queue / inbox ingestion
Drop URLs into some inbox (file, Raindrop, Readwise, Telegram bot, share sheet) and have summaries land somewhere readable (Obsidian vault, email, Notion). Removes the friction of invoking a CLI manually for every video.

### Speaker diarization
Add `pyannote` (or similar) so multi-speaker content — interviews, panels, podcasts with 2+ hosts — gets "who said what" attribution. Meaningfully improves summaries of conversational content. Skipped in v1 because solo talks/lectures don't need it and it roughly doubles pipeline complexity.

### Hosted web service
Public version where anyone can paste a URL. Requires resolving legal/ToS questions around re-hosting transcribed content from third-party platforms, plus auth, rate limiting, abuse handling, and a cost model (local LLM won't scale to arbitrary public traffic).

### Evolving profile — from watch log to taste model

Right now `profile.md` has a static LinkedIn-derived section and an ever-growing `## Watch history` list. This doesn't scale — after 100 videos the list is prompt bloat, and storing every URL the user watches is a privacy concern.

The idea: **the watch history is a staging area, not permanent storage.** Periodically (every N runs, or on `vidsum profile refresh`), an LLM pass reads the accumulated watch history and *folds it back into the profile itself* — updating interest weights, surfacing new topic clusters, retiring stale ones. Then the raw history is truncated (keep last N entries as recency signal, drop the rest).

What this looks like concretely:

1. **Accumulate** — after each run, append title + topic tags to watch history (current behaviour).
2. **Distill** — every ~20 runs (or manually via `vidsum profile refresh`), run an LLM call that:
   - Reads the current profile sections + full watch history
   - Produces an updated `## Interest signals` section with re-weighted topics
   - Identifies new emerging interests ("started watching economics content")
   - Demotes interests with no recent signal ("hasn't watched adtech content in 2 months")
3. **Truncate** — keep only the last 10 watch history entries. The distilled knowledge lives in the profile sections, not the raw log.
4. **Diff visibility** — show the user what changed ("Added: macroeconomics. Demoted: adtech.") so they can override.

This way the profile stays compact (~500 words), genuinely reflects evolving taste, and never stores more viewing history than needed. The raw watch data in `runs.jsonl` remains as a complete but separate audit log that doesn't get injected into prompts.

**Privacy principle:** `profile.md` should contain *derived understanding* (what you're interested in), not *raw behaviour logs* (every URL you've ever watched). The distinction matters.

### Cloud backend tuning — single-pass without expand

The two-pass (draft → expand) flow was built to compensate for small local models being terse. Cloud models (Sonnet 4.6) don't need this — they produce good length and depth in one shot. Currently the expand pass is skipped for cloud via `backend.name == "local"` check.

When we invest in cloud quality, consider:
- **Cloud-specific prompt variant** — cloud models can handle more nuanced instructions. The summarize prompt could be richer (e.g. ask for reasoning chains, comparative analysis) without worrying about overwhelming the model.
- **Longer single-pass threshold for cloud** — cloud models have larger effective context. The 12k token threshold that triggers refine chain could be raised to 30-50k for cloud, keeping more videos on the higher-quality single-pass path.
- **Structured output via API** — Anthropic's API supports structured output natively. Could re-enable JSON output for cloud only (clean parsing, no regex) while keeping markdown for local.

### Hardware scale-out
If usage grows, offload transcription + LLM inference to a dedicated Mac Mini so the main workstation stays free.
