# vidsum

Personalized video summaries from your profile and watch history.

`vidsum` is a CLI for personalized video summaries.

It summarizes long-form video and audio URLs, then shapes the output around the reader: what they already know, what they care about, and what is worth expanding versus compressing.

The repo is designed to be easy for a person or another local model to install straight from Git and call non-interactively.

## Why It Exists

Most video summarizers are generic. They summarize the source, but not for the person reading it.

`vidsum` is trying to do something more useful:

- use your `profile.md` as a standing preference and expertise layer
- optionally build that profile from your LinkedIn profile URL
- learn from your watch history over time
- compress the parts you already know
- emphasize the parts you are more likely to care about

The result should feel less like "here is what the video said" and more like "here is the version of this video that matters to you."

## Install

```bash
git clone https://github.com/gptgrv/vidsum.git
cd vidsum
uv sync
```

`uv sync` installs the Python dependencies, including `yt-dlp` and `faster-whisper`.
If you want local summarization, install Ollama separately, then run `vidsum onboard`.
If you want cloud summarization, `vidsum onboard` will guide you through API key setup.

For a guided first-time setup:

```bash
uv run vidsum onboard
```

Run directly from the repo:

```bash
uv run vidsum summarize "<url>"
```

or the shorthand:

```bash
uv run vidsum "<url>"
```

Install straight from GitHub:

```bash
uv tool install git+https://github.com/gptgrv/vidsum
```

or:

```bash
pip install git+https://github.com/gptgrv/vidsum
```

If you prefer an editable local install:

```bash
uv pip install -e .
vidsum "<url>"
```

## Quickstart

```bash
vidsum onboard
vidsum "https://www.youtube.com/watch?v=..."
vidsum "https://www.youtube.com/watch?v=..." --json
vidsum "https://www.youtube.com/watch?v=..." --cloud
vidsum profile init --linkedin-url https://www.linkedin.com/in/your-handle/
```

## What Makes It Different

- **Personalized by default.** The main profile source is a local `profile.md`, so the tool works from a plain Git checkout without requiring a platform-specific memory system.
- **LinkedIn-powered bootstrap.** You can generate an initial profile from your LinkedIn URL instead of writing it from scratch.
- **Watch-history aware.** Successful runs append to watch history so the personalization layer gets sharper over time.
- **Model-friendly interface.** Clean stdout/stderr separation, stable `--json`, predictable output paths, and no interactive prompts.
- **Local-first, cloud-optional.** Use local models by default, switch to cloud only when quality matters more than cost.

## How It Works

- tries YouTube captions first and skips transcription when available
- falls back to `yt-dlp` + `faster-whisper` for audio transcription
- uses a single-pass summary for shorter transcripts and a refine chain for longer ones
- writes Markdown by default and can emit a stable `--json` payload for automation
- keeps logs and cached intermediates separate from final summaries

## Personalization Demo

Generic summarizer:

> "This talk covers AI agent orchestration, common multi-agent patterns, and lessons from real deployments."

`vidsum` for a product leader building with LLM tools:

> "The useful part of this talk is not the abstract taxonomy of agent patterns, but the operating constraints behind them: where orchestration adds leverage, where it adds latency and debugging pain, and which patterns survive contact with production."

That difference is the product.

## Profile Setup

`vidsum` works with no external setup, but it gets better when you give it a profile.

For most people, the easiest path is:

```bash
vidsum onboard
```

The default personalization source is a local `profile.md` in the working directory. Start from [`profile.example.md`](./profile.example.md), or generate one with:

```bash
vidsum profile init --linkedin-url https://www.linkedin.com/in/your-handle/
```

If LinkedIn blocks automated access, fall back to:

```bash
vidsum profile init --linkedin-pdf ~/Downloads/LinkedIn.pdf
```

Optional supplemental sources:

- OpenClaw workspace files
- Claude project memory

Those are extra context only, not required setup.

## Basic Usage

```bash
vidsum "<url>"
vidsum "<url>" --json
vidsum "<url>" --cloud
vidsum "<url>" --compare
vidsum "<url>" --out summaries/my-note.md
vidsum profile init --linkedin-url https://www.linkedin.com/in/your-handle/
```

## CLI Contract

- `stdout`: summary content only, or JSON with `--json`
- `stderr`: progress, timings, warnings, errors
- no interactive prompts
- meaningful exit codes for bad URL, download failure, transcription failure, and LLM failure

## Configuration

Useful env vars:

- `VIDSUM_OUT`: override the output directory for Markdown summaries
- `VIDSUM_RUNS_LOG`: override the `runs.jsonl` path
- `VIDSUM_CACHE`: override the cache directory
- `VIDSUM_PROFILE_PATH`: override the local profile file path
- `VIDSUM_OPENCLAW_WORKSPACE`: override the optional OpenClaw workspace path
- `VIDSUM_CLAUDE_MEMORY_DIR`: override the optional Claude memory path

## Privacy

- your LinkedIn URL is only fetched to build your local profile
- your LinkedIn PDF stays local when you use the fallback path
- your `profile.md` stays local unless you choose to share it
- watch history is stored locally in your profile/workspace context

## Repo Direction

This repo is intentionally CLI-first. It does not require agent-specific skills or platform wrappers to be useful. If another local model wants to use it, the expected integration is: clone repo, install dependencies, shell out to `vidsum`, and consume Markdown or JSON.
