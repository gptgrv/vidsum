"""Summarisation paths.

Two strategies, both now using a two-pass approach:

1. ``summarize_single_pass`` — feeds the entire transcript to the model in one
   call. Used when the transcript is short enough to fit comfortably.

2. ``summarize_refine_chain`` — used only for long transcripts that exceed the
   single-pass threshold. Walks chunks in order, maintains a rolling markdown
   summary, then runs a final pass.

Both strategies follow a two-pass flow:
  Pass 1 (draft): produce a markdown summary from the source material.
  Pass 2 (expand): identify the 2-3 most important sections and expand them
                    with specifics from the transcript.

Output is plain markdown — no JSON. The Summary dataclass is populated by
parsing the markdown after the fact.
"""

from __future__ import annotations

import re
import sys

from .backends import Backend
from .chunk import format_timestamp
from .config import REFINE_FINAL_MAX_TOKENS, ROLLING_SUMMARY_BUDGET, ROLLING_SUMMARY_MAX_TOKENS
from .prompts import expand_prompt, refine_chunk_prompt, summarize_prompt
from .types import Chunk, Summary, Transcript

REFINE_USER_TEMPLATE = """\
# Rolling summary so far

{rolling}

# New transcript chunk

Time range: {start} – {end}

{text}
"""

SUMMARY_USER_TEMPLATE = """\
# Video metadata

- Title: {title}
- Duration: {duration}
- URL: {url}

# Source material

{content}

Write the summary now.
"""

EXPAND_USER_TEMPLATE = """\
# Video metadata

- Title: {title}
- Duration: {duration}

# Draft summary to improve

{draft}

# Original transcript (use this to add specifics)

{transcript}

Expand the most important sections now.
"""


# ---------------------------------------------------------------------------
# Single-pass (preferred for short/medium videos)
# ---------------------------------------------------------------------------


def summarize_single_pass(
    transcript: Transcript,
    *,
    backend: Backend,
    profile: str,
    title: str,
    duration_seconds: float,
    url: str,
    quiet: bool = False,
) -> tuple[Summary, dict]:
    """Summarise the full transcript.

    Local backends get a two-pass flow (draft → expand) because small models
    are terse and need a second pass to add depth.  Cloud backends are strong
    enough to produce a good summary in one shot.
    """
    total_input = 0
    total_output = 0
    use_expand = backend.name == "local"

    # --- Pass 1: Draft ---
    if not quiet:
        label = "pass 1 — draft" if use_expand else "single-pass"
        print(f"  summarize: {label} (full transcript)", file=sys.stderr, flush=True)

    system = _summary_system(profile)
    user = _summary_user(
        title=title,
        duration_seconds=duration_seconds,
        url=url,
        content=transcript.full_text,
    )
    result = backend.complete(system, user, max_tokens=8192)
    draft = result.text.strip()
    total_input += result.input_tokens
    total_output += result.output_tokens
    n_calls = 1

    if not quiet:
        draft_words = len(draft.split())
        print(f"  summarize: draft is {draft_words} words", file=sys.stderr, flush=True)

    # --- Pass 2: Expand (local only) ---
    if use_expand:
        if not quiet:
            print("  summarize: pass 2 — expanding key sections", file=sys.stderr, flush=True)

        expand_system = expand_prompt().format(
            profile=profile or "(no profile available)",
        )
        expand_user = EXPAND_USER_TEMPLATE.format(
            title=title,
            duration=format_timestamp(duration_seconds),
            draft=draft,
            transcript=transcript.full_text,
        )
        expand_result = backend.complete(expand_system, expand_user, max_tokens=8192)
        final_md = expand_result.text.strip()
        total_input += expand_result.input_tokens
        total_output += expand_result.output_tokens
        n_calls = 2

        if not quiet:
            final_words = len(final_md.split())
            print(
                f"  summarize: final is {final_words} words "
                f"({final_words - len(draft.split()):+d})",
                file=sys.stderr,
                flush=True,
            )
    else:
        final_md = draft

    summary = _parse_markdown_summary(final_md)
    stats = {
        "input_tokens": total_input,
        "output_tokens": total_output,
        "n_calls": n_calls,
    }
    return summary, stats


def _summary_system(profile: str) -> str:
    return summarize_prompt().format(
        profile=profile or "(no profile available)",
    )


def _summary_user(
    *,
    title: str,
    duration_seconds: float,
    url: str,
    content: str,
) -> str:
    return SUMMARY_USER_TEMPLATE.format(
        title=title,
        duration=format_timestamp(duration_seconds),
        url=url,
        content=content,
    )


# ---------------------------------------------------------------------------
# Refine chain (used only for long videos)
# ---------------------------------------------------------------------------


def summarize_refine_chain(
    chunks: list[Chunk],
    *,
    backend: Backend,
    profile: str,
    title: str,
    duration_seconds: float,
    url: str,
    quiet: bool = False,
) -> tuple[Summary, dict]:
    system = (
        refine_chunk_prompt()
        .replace("{profile}", profile or "(no profile available)")
        .replace("{rolling_summary_budget}", str(ROLLING_SUMMARY_BUDGET))
    )

    rolling = "(none yet — this is the first chunk)"
    total_input = 0
    total_output = 0

    for chunk in chunks:
        if not quiet:
            print(
                f"  refine: chunk {chunk.index + 1}/{len(chunks)} "
                f"({format_timestamp(chunk.start)}–{format_timestamp(chunk.end)}, "
                f"~{chunk.token_estimate} tok)",
                file=sys.stderr,
                flush=True,
            )
        user = REFINE_USER_TEMPLATE.format(
            rolling=rolling,
            start=format_timestamp(chunk.start),
            end=format_timestamp(chunk.end),
            text=chunk.text,
        )
        result = backend.complete(system, user, max_tokens=ROLLING_SUMMARY_MAX_TOKENS)
        rolling = result.text.strip()
        total_input += result.input_tokens
        total_output += result.output_tokens

    # Final pass: turn the rolling markdown into the structured summary.
    if not quiet:
        print("  refine: final structured pass", file=sys.stderr, flush=True)
    final_system = _summary_system(profile)
    final_user = _summary_user(
        title=title,
        duration_seconds=duration_seconds,
        url=url,
        content=rolling,
    )
    final_result = backend.complete(final_system, final_user, max_tokens=REFINE_FINAL_MAX_TOKENS)
    draft = final_result.text.strip()
    total_input += final_result.input_tokens
    total_output += final_result.output_tokens

    use_expand = backend.name == "local"

    if not quiet:
        draft_words = len(draft.split())
        print(f"  refine: draft is {draft_words} words", file=sys.stderr, flush=True)

    n_calls = len(chunks) + 1

    # Expand pass (local only): deepen the most important sections.
    # For refine chain we use the rolling summary as "transcript" context since
    # the full transcript is too long to fit. The rolling summary has the detail.
    if use_expand:
        if not quiet:
            print("  refine: expanding key sections", file=sys.stderr, flush=True)

        expand_system = expand_prompt().format(
            profile=profile or "(no profile available)",
        )
        expand_user = EXPAND_USER_TEMPLATE.format(
            title=title,
            duration=format_timestamp(duration_seconds),
            draft=draft,
            transcript=rolling,
        )
        expand_result = backend.complete(
            expand_system, expand_user, max_tokens=REFINE_FINAL_MAX_TOKENS
        )
        final_md = expand_result.text.strip()
        total_input += expand_result.input_tokens
        total_output += expand_result.output_tokens
        n_calls += 1

        if not quiet:
            final_words = len(final_md.split())
            print(
                f"  refine: final is {final_words} words "
                f"({final_words - len(draft.split()):+d})",
                file=sys.stderr,
                flush=True,
            )
    else:
        final_md = draft

    summary = _parse_markdown_summary(final_md)
    stats = {
        "input_tokens": total_input,
        "output_tokens": total_output,
        "n_calls": n_calls,
    }
    return summary, stats


# ---------------------------------------------------------------------------
# Markdown parser — extracts Summary from plain markdown output
# ---------------------------------------------------------------------------


def _parse_markdown_summary(text: str) -> Summary:
    """Parse a markdown summary into the Summary dataclass.

    Expected structure:
      ## TL;DR
      <prose>

      ## <body headings...>
      <content>

      ## Actionable takeaways  (optional)
      - item
      - item
    """
    # Strip any leading meta-commentary the model might have added.
    text = _strip_preamble(text)

    tldr = ""
    body_parts: list[str] = []
    takeaways: list[str] = []

    # Split on ## headings (level 2). Keep the heading with its content.
    sections = re.split(r"(?=^## )", text, flags=re.MULTILINE)

    state = "body"  # default: anything before the first ## goes to body
    for section in sections:
        section = section.strip()
        if not section:
            continue

        heading_match = re.match(r"^## (.+)", section)
        if heading_match:
            heading = heading_match.group(1).strip().lower()
            content = section[heading_match.end() :].strip()

            if heading in ("tl;dr", "tldr", "tl; dr"):
                tldr = content
                state = "tldr"
            elif "actionable" in heading or "takeaway" in heading:
                takeaways = _parse_bullet_list(content)
                state = "takeaways"
            else:
                # It's a body section — keep the full section including heading.
                body_parts.append(section)
                state = "body"
        else:
            # Content before any heading — treat as body.
            if state == "body":
                body_parts.append(section)

    body = "\n\n".join(body_parts).strip()

    # Fallback: if parsing found nothing, dump everything into body.
    if not tldr and not body:
        body = text

    return Summary(
        tldr=tldr,
        body=body,
        actionable_takeaways=takeaways,
    )


def _strip_preamble(text: str) -> str:
    """Remove any meta-commentary before the first ## heading."""
    match = re.search(r"^## ", text, re.MULTILINE)
    if match and match.start() > 0:
        before = text[: match.start()].strip()
        # If the preamble is short and looks like meta-commentary, drop it.
        if len(before) < 200 and not before.startswith("#"):
            return text[match.start() :]
    return text


def _parse_bullet_list(text: str) -> list[str]:
    """Extract bullet items from markdown text."""
    items: list[str] = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith(("- ", "* ", "• ")):
            item = line[2:].strip()
            if item:
                items.append(item)
        elif line.startswith(tuple(f"{i}." for i in range(1, 20))):
            item = re.sub(r"^\d+\.\s*", "", line).strip()
            if item:
                items.append(item)
    return items
