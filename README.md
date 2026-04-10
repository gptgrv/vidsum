# vidsum

Video summaries, written for who you are.

A doctor and an AI engineer watching the same lecture should not get the same summary. `vidsum` shapes every summary around the reader — their expertise, their interests, what they already know and what they're looking for.

The repo is designed to be easy for a person or another local model to install straight from Git and call non-interactively.

## Why It Exists

Most video summarizers are generic. They compress the video, but not *for you*.

`vidsum` does something different:

- builds a profile from your LinkedIn (or you write one)
- learns from your watch history over time
- compresses what you already know
- expands what you're more likely to care about

The result feels less like "here is what the video said" and more like "here is the part that matters to you."

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

Same video. Two readers. Same `vidsum` command.

<table>
<tr>
<td colspan="2">

[![How Do Ozempic, Mounjaro & Other GLP-1 Agonists Work? — Dr. Zachary Knight & Dr. Andrew Huberman](https://img.youtube.com/vi/zRXC2pEbj5w/maxresdefault.jpg)](https://www.youtube.com/watch?v=zRXC2pEbj5w)

</td>
</tr>
<tr>
<td width="50%" valign="top">

**For a physician**

> The clinically relevant piece is the dose escalation logic: nausea from liraglutide undergoes tachyphylaxis, which is what allowed the monthly step-ups that finally reached effective weight-loss doses. The brainstem access story is also worth noting — semaglutide reaches the NTS and area postrema specifically because those are circumventricular organs with a weakened blood-brain barrier, not because of receptor density. For patients asking about muscle loss: the 25–33% lean mass loss number is real but likely overstated as a concern if they're doing resistance training and eating adequate protein.

</td>
<td width="50%" valign="top">

**For a tech industry reader**

> The most interesting thing here isn't the biology — it's the discovery arc. The natural hormone (GLP-1) is useless as a drug because it degrades in 2 minutes. DPP-4 inhibitors boost it 3x, enough to treat diabetes, but nobody loses weight — which accidentally proved that natural GLP-1 doesn't control body weight. Then a peptide from Gila monster venom turned out to be a stabilised version (2-hour half-life), and from there it was pure iteration: 2 min → 2 hours → 13 hours → 7 days. The breakthrough dose came from a side effect — patients got nauseous, but the nausea faded, so they kept increasing the dose until it worked. The whole thing reads like a 40-year product development cycle where the key insights came from accidents and side effects, not from the original hypothesis.

</td>
</tr>
</table>

Same video. Completely different summaries. That's the product.

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
