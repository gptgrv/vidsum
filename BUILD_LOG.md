# Building vidsum: A CLI Video Summariser

> **Purpose of this file:** This is a living build log. Every agent session that works on this project should add an entry documenting what was built, what decisions were made, and what was learned. The goal is to turn this into content for a Substack story, LinkedIn post, and X thread about building an AI-powered tool with AI-powered tools. Keep adding user's reason behing his prompt and final changes made. Append at the bottom.

---

## The Premise

What if you could paste a YouTube URL and get back a summary that actually *understands* what matters to you?

Not a generic "this video discusses machine learning" — but a summary that knows you're a builder, knows your interests, and emphasises the parts you'd actually care about. That's `vidsum`.

But the real story isn't just the tool. It's *how* we're building it: as a clean, scriptable CLI from the ground up. A human should be able to use `vidsum` directly, and another local model should be able to clone the repo, install it, and shell out to the command without any extra wrapper layer. And the tool itself is being built *by* AI agents, session by session, with this log as the narrative thread.

---

## The Architecture (What & Why)

**The pipeline:**
```
URL → Captions/Audio Download → Transcription → Chunking → Summarisation → Personalised Markdown
```

**Key design choices:**

1. **Local-first, cloud-optional.** Default backend is Qwen 2.5 7B running via Ollama on an M4 MacBook with 16GB RAM. Free, private, runs offline. `--cloud` flag switches to Claude Sonnet 4.6 when quality matters more than cost.

2. **YouTube caption fast-path.** If English captions exist, skip the entire audio download + Whisper transcription pipeline. This turns a 15-minute wait into seconds.

3. **Smart dispatch on length.** Short/medium videos (under ~60 min of speech) get a single-pass summary — one LLM call sees the full transcript. Longer videos get a refine chain: semantic chunking, rolling summary across chunks, then a final polish pass. We tried refine-chain-for-everything first and the outputs were thin and bland. Single-pass is dramatically better when it fits.

4. **Personalisation is invisible.** The tool reads your local profile first and can optionally supplement it from external workspace files. It weaves that context into emphasis and vocabulary — not as a separate "why this matters to you" section. If the profile has no relevant angle, the summary reads as a normal high-quality summary. No forced connections.

5. **Agent-first interface.** stdout is summary content only. stderr is progress/logs. Exit codes are meaningful. `--json` gives structured output. No interactive prompts, ever. This isn't a CLI that happens to be scriptable — it's an agent tool that happens to have a nice human interface.

**The stack:**
- Python, managed with `uv`
- `yt-dlp` for downloading from any platform
- `faster-whisper` with `distil-large-v3` for transcription
- Ollama (Qwen 2.5 7B) for local summarisation
- Anthropic SDK (Sonnet 4.6) for cloud summarisation
- `tiktoken` for token counting
- `click` for the CLI

---

## Session Log

### Session 1: Design Interview & Scaffolding

**What happened:** Started from zero. Ran a design interview (using the `/grill-me` pattern) to nail down scope, architecture, and non-goals before writing a line of code. The output was three documents: `DECISIONS.md` (locked choices with rationale), `PLAN.md` (implementation plan with build order), and `ROADMAP.md` (what's deferred and why).

Then scaffolded the entire project: `pyproject.toml`, all module stubs, CLI entry point, and `.gitignore`.

**What was interesting:**
- The design interview caught several things that would have been painful later. For example, we almost went with refine-chain-for-everything before realising that single-pass is better for short videos. We almost added a "Why this matters to you" section before realising forced personalisation is worse than subtle personalisation.
- Writing `DECISIONS.md` as a separate artifact from the plan was valuable. The plan says *what* to build; decisions says *why* those choices were made. When a future session disagrees with a choice, the rationale is right there.
- Thinking through the CLI interface contract early paid off. Clean stdout/stderr separation and stable JSON are what make the tool portable across humans and models.

**Code written:** ~1,500 lines across 17 Python files, plus project config and documentation. Full module structure in place: CLI, pipeline orchestrator, download, captions, transcription, chunking, refine chain, backends (local + cloud), profile loader, output serialiser, observability, and type definitions.

**Key decision documented:** "Hobby-project disposition. Optimize for fun to work on and evolves as we learn, not for rigor or exhaustive coverage."

---

### Session 2: Personalisation — From Empty Profile to LinkedIn-Powered Identity

**What happened:** Audited the existing personalisation pipeline and found it was wired up correctly but running on fumes. External workspace files were being treated too generously, while the actual user profile signal was thin. The real user profile was essentially: name, timezone, and fitness constraints.

Meanwhile, the 8 videos already summarised told a clear story: AI agents, startups, e-commerce strategy, health/longevity, investing. The user's behaviour was a richer profile than anything written down.

**What we built:**
1. **LinkedIn PDF profile builder** — `vidsum profile init --linkedin-pdf <path>`. Exports your LinkedIn as PDF (one click), feeds it to an LLM with a purpose-built prompt that extracts *summarisation-relevant* traits: domain expertise, interest signals, vocabulary level, what to compress. Not a generic bio — specifically tuned for "how should summaries be personalised for this person?"
2. **Auto watch history** — every successful `vidsum` run now appends the video title, URL, duration, and backend to a `## Watch history` section in `profile.md`. Over time, this becomes the strongest personalisation signal: not what your LinkedIn says you care about, but what you *actually watch*.
3. **CLI restructure** — `vidsum` is now a command group (`vidsum summarize <url>`, `vidsum profile init`, `vidsum profile show`) with backwards-compatible URL detection so `vidsum <url>` still works.
4. **Profile.md seeded** — built GG's initial profile from LinkedIn + web sources. Covers professional identity (Coupang product leader), domain expertise (e-commerce, mobility, adtech, AI tooling), interest signals, vocabulary level, and topics to compress.

**What was interesting:**
- LinkedIn's public API is basically useless for a hobby tool (requires company-level partnership). Web scraping gets blocked. But the **PDF export** is perfect: one click, rich structured data, zero API keys, zero cost. Sometimes the lowest-tech solution wins.
- The profile prompt required careful design. Early versions produced generic bios ("experienced product leader passionate about technology"). The fix was being extremely specific about what "useful for summarisation" means: not who you are, but how summaries should differ because of who you are.
- Injecting `IDENTITY.md` and `SOUL.md` (the assistant's personality config) into summarisation prompts was pure noise. Config already correctly excluded them — good catch by whoever wrote `config.py` in Session 1.
- The watch history is the sleeper feature. After 20-30 videos, the LLM will see a clear map of what this person actually cares about — far more reliable than any self-reported profile.

**Code written:** New `profile_builder.py` module (~100 lines), `build_profile.md` prompt template, CLI restructured with command groups + backwards compat, watch history auto-append wired into the pipeline.

### Session 2b: Killing JSON, Adding the Expand Pass

**The problem we found:** Every summary was undershooting its own length targets by 50-70%. A 57-minute Stanford lecture on AI agents was getting compressed to 635 words when the prompt asked for 1500-3000. A 39-minute startup talk was producing 557 words against a target of 1500-3000.

**Root cause analysis showed three compounding factors:**
1. Qwen 7B is naturally terse — small models don't sustain long coherent output.
2. The JSON output format was taxing the model — producing valid JSON with properly escaped newlines in a 3000-word body is *hard* for a 7B. The model "played it safe" by writing less.
3. A single prompt saying "write 1500-3000 words" doesn't work on small models. They read the instruction and ignore it.

**What we changed:**
1. **Dropped JSON output entirely.** The LLM now writes plain markdown. No escaping, no structural overhead, just natural writing. We parse the markdown into our `Summary` dataclass after the fact with a regex-based section splitter.
2. **Added a two-pass flow.** Pass 1: draft the summary. Pass 2: the model reads its own draft + the original transcript, identifies the 2-3 most important/unique sections, and expands them with specifics. This is the key insight — instead of asking the model to write long once, you ask it to write short and then *deepen* where it matters.

**The expand prompt is deliberately opinionated:** it tells the model to find what's *unique and surprising* in this specific video, not just comprehensively cover every point. A summary that goes deep on the 2-3 genuinely interesting ideas is more valuable than one that evenly covers 10 ideas at surface level.

**Design decision:** For the refine chain (long videos), the expand pass gets the rolling summary as context instead of the full transcript (which is too long to fit). This means expand quality for long videos depends on the rolling summary being good — a known limitation we're accepting for now.

### Session 3: Making The Repo Portable — From Skill Wrapper to Standalone CLI

**What happened:** We stepped back and looked at the repo from the point of view of a different local model trying to use it cold. The answer was obvious: the core product was already a decent CLI, but the repo still *presented itself* like it needed an OpenClaw skill to be complete. That was the wrong abstraction for where the project is right now.

So this session was about cleaning up the repo surface area to match the actual product: a standalone command-line tool that can be cloned from Git, installed with `uv`, and invoked non-interactively by either a person or another model.

**What we changed:**
1. **Added a real README.** The repo now has a top-level `README.md` that explains what `vidsum` is, how to install it from Git, how to run it, what the CLI contract is, and which environment variables matter. This sounds basic, but it is the difference between "code in a folder" and "tool someone else can actually pick up."
2. **Removed the skill packaging from the repo.** The old `skill/SKILL.md` artifact was deleted. Not because skills are bad, but because they were making the project look more coupled to one agent platform than it really is.
3. **Made local `profile.md` the default personalisation path.** External memory sources like OpenClaw workspace files and Claude memory are still supported, but they are now explicitly optional supplements. That makes the repo much more portable.
4. **Added env-var overrides for portability.** Paths for cache, outputs, run logs, local profile, OpenClaw workspace, and Claude memory can now all be overridden cleanly. That matters if the tool is being run from a different machine, a different workspace layout, or by another local model with its own conventions.
5. **Added `python -m vidsum` support.** Small thing, but useful. It makes the package feel more like a normal Python CLI and improves ergonomics for people testing from source.
6. **Cleaned repo hygiene.** Updated `.gitignore`, added package metadata for the README, and refreshed the docs (`DECISIONS.md`, `PLAN.md`, `ROADMAP.md`) so they describe the product we actually want to ship.

**What was interesting:**
- The codebase was ahead of the docs. The implementation already had the right shape: reusable core, thin CLI, JSON mode, clean stdout/stderr separation. The mismatch was mostly narrative and packaging.
- Repo framing matters more than it seems. If a project says "agent-first + skill" everywhere, people infer hidden setup requirements even if the code itself doesn't have them.
- We found an unrelated but useful issue during cleanup: the tests still expected an older JSON-based summary parser even though the implementation had already moved to markdown-first generation. That is exactly the kind of quiet drift that good cleanup sessions catch.

**What broke:** `pytest` initially failed because `tests/test_llm_requests.py` was importing `_parse_summary_json`, which no longer existed in the current markdown-based summarisation flow. We updated the tests to validate the actual parser and current prompt contract instead of resurrecting dead code just to satisfy stale expectations.

**Verification:** `uv run pytest` passed with 10 tests green and 1 smoke test skipped by design. We also ran `uv run python -m vidsum --help` to confirm the package entry point works cleanly.

**Why this matters:** This session didn't add a flashy user-facing feature. It did something more foundational: it made `vidsum` easier to adopt. If OpenClaw, Hermes, or any other local model wants to use this later, the path is now straightforward: clone repo, install dependencies, shell out to the CLI, consume markdown or JSON. No extra wrapper required.

### Session 4: First Public Release Prep — Onboarding, URL-First Profile Setup, Repo Polish

**Why the user asked for this:** We were preparing to publish the first version of `vidsum` to GitHub so other people, and eventually other local models, could install it from Git. That forced a more product-minded pass over the repo: not just "does the code work?" but "does the first-run experience make sense?"

**What happened:** We audited the onboarding path from a fresh user's point of view and found a real mismatch. The CLI now had `vidsum onboard` and `vidsum status`, but the README still mostly described the old PDF-heavy setup. Worse, the main summarize command was accidentally ignoring the backend saved during onboarding and silently falling back to local mode.

**What we changed:**
1. **Fixed backend persistence.** If onboarding saves `cloud` or `openai` as the preferred backend, `vidsum <url>` now actually uses it by default. This sounds small, but it is the difference between a trustworthy onboarding flow and one that lies.
2. **Made LinkedIn URL the primary profile setup path.** `vidsum profile init` now accepts `--linkedin-url`, and the README/examples now present URL-first setup. PDF is still supported, but clearly as a fallback when LinkedIn blocks automated access.
3. **Implemented the missing URL profile builder path.** The code already referenced `build_profile_from_linkedin_url(...)` in onboarding, but the implementation was missing. We added a best-effort LinkedIn URL fetch/extract path and wired it into the profile builder.
4. **Improved public repo assets.** Added a proper README with GitHub install instructions for `gptgrv/vidsum`, a `LICENSE`, and `profile.example.md`. Renamed the local repo directory to `vidsum` to match the public name.
5. **Added regression tests around onboarding and profile init.** This included tests for saved backend behavior and the new `profile init --linkedin-url` path, so the first-run UX is now under test instead of living only in docs.

**What was interesting:**
- Onboarding bugs are extra dangerous because they create false confidence. The user feels "set up," but then the product behaves differently from what setup implied.
- The repo name, folder name, install commands, and docs all have to line up before a project feels publishable. Tiny mismatches create disproportionate friction.
- LinkedIn URL is clearly the lower-friction story for users, but that only works if the fallback path is explicit. LinkedIn blocking automation is not an edge case; it is part of the real product experience.

**Verification:** `uv run pytest` passed with 15 tests green and 1 smoke test skipped by design. We also rechecked `uv run python -m vidsum --help` and `uv run python -m vidsum profile init --help` to confirm the public command surface is coherent.

**Why this matters:** This session turned `vidsum` from "promising repo" into "reasonable v0.1 you could actually publish." The personalization story is now clearer, the onboarding story is real, and the install path finally matches the way we want people to discover and use the tool.

---

*Future sessions: add your entry here. What did you build? What broke? What surprised you? What did you learn about building with agents? Keep it honest and specific — this becomes the story.*
