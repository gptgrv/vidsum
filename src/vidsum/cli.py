"""CLI entry point. Automation-friendly: stdout = summary content, stderr = progress."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from dotenv import load_dotenv

from .config import DEFAULT_WHISPER_MODEL, output_dir
from .observability import append_run
from .output import render_json, render_markdown, write_markdown
from .pipeline import PipelineResult, duration_str, run_pipeline

# Exit codes for the CLI contract
EXIT_OK = 0
EXIT_GENERIC = 1
EXIT_BAD_URL = 2
EXIT_DOWNLOAD = 3
EXIT_TRANSCRIBE = 4
EXIT_LLM = 5


class _VidsumGroup(click.Group):
    """Custom group that treats unknown subcommands as URLs for `summarize`.

    This preserves backwards compatibility: `vidsum <url>` still works alongside
    `vidsum summarize <url>` and `vidsum profile init ...`.
    """

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        # If the first arg isn't a known subcommand, route everything to "summarize".
        # This covers both bare URLs (`vidsum <url>`) and flags-first
        # (`vidsum --cloud <url>`).
        if args and args[0] not in self.commands and args[0] not in ("-h", "--help"):
            args = ["summarize"] + args
        return super().parse_args(ctx, args)


@click.group(
    cls=_VidsumGroup,
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.pass_context
def main(ctx: click.Context) -> None:
    """vidsum — personalised video/audio summariser."""
    load_dotenv()  # Load .env without overriding explicit environment variables.
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.command()
@click.option("--backend", type=click.Choice(["local", "cloud", "openai"]), help="Backend to configure.")
@click.option("--api-key", default=None, help="API key (stored in .env, never leaves your device).")
@click.option("--model", default=None, help="Override the default model for the chosen backend.")
@click.option("--linkedin-url", default=None, help="LinkedIn profile URL for personalisation.")
@click.option(
    "--linkedin-pdf",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="LinkedIn PDF fallback for personalisation.",
)
def onboard(
    backend: str | None,
    api_key: str | None,
    model: str | None,
    linkedin_url: str | None,
    linkedin_pdf: Path | None,
) -> None:
    """Set up vidsum: choose backend, configure keys, build profile."""
    from .onboard import run_onboard_interactive, run_onboard_noninteractive

    # If any flags are provided, run non-interactively (agent mode).
    if any([backend, api_key, model, linkedin_url, linkedin_pdf]):
        run_onboard_noninteractive(
            backend=backend,
            api_key=api_key,
            model=model,
            linkedin_url=linkedin_url,
            linkedin_pdf=linkedin_pdf,
        )
    else:
        run_onboard_interactive()


@main.command("status")
def status_cmd() -> None:
    """Show current vidsum configuration."""
    from .onboard import show_status

    show_status()


@main.command()
@click.argument("url")
@click.option("--cloud", is_flag=True, help="Use Anthropic Claude (Sonnet 4.6).")
@click.option("--openai", "use_openai", is_flag=True, help="Use OpenAI (GPT-4o).")
@click.option("--compare", is_flag=True, help="Run both local and cloud, write both outputs.")
@click.option("--fresh", is_flag=True, help="Force re-download and re-transcribe.")
@click.option(
    "--whisper-model",
    default=DEFAULT_WHISPER_MODEL,
    show_default=True,
    help="faster-whisper model id.",
)
@click.option("--keep-audio", is_flag=True, help="Don't delete cached audio after run.")
@click.option("--json", "json_out", is_flag=True, help="Emit JSON to stdout instead of markdown.")
@click.option("--quiet", is_flag=True, help="Suppress progress on stderr.")
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write summary to this path instead of stdout.",
)
def summarize(
    url: str,
    cloud: bool,
    use_openai: bool,
    compare: bool,
    fresh: bool,
    whisper_model: str,
    keep_audio: bool,
    json_out: bool,
    quiet: bool,
    out: Path | None,
) -> None:
    """Summarise a video, podcast, or audio URL."""
    import os

    # Resolve backend: explicit flag > .env > default (local)
    if cloud:
        backend_kind = "cloud"
    elif use_openai:
        backend_kind = "openai"
    else:
        backend_kind = os.environ.get("VIDSUM_BACKEND", "local")

    # Auto-nudge if backend needs a key that isn't set
    if backend_kind == "cloud" and not os.environ.get("ANTHROPIC_API_KEY"):
        print("No Anthropic API key found. Run: vidsum onboard", file=sys.stderr)
        sys.exit(EXIT_GENERIC)
    if backend_kind == "openai" and not os.environ.get("OPENAI_API_KEY"):
        print("No OpenAI API key found. Run: vidsum onboard", file=sys.stderr)
        sys.exit(EXIT_GENERIC)

    try:
        if compare:
            _run_compare(
                url,
                whisper_model=whisper_model,
                fresh=fresh,
                json_out=json_out,
                quiet=quiet,
                out=out,
            )
        else:
            result = run_pipeline(
                url,
                backend_kind=backend_kind,
                whisper_model=whisper_model,
                fresh=fresh,
                quiet=quiet,
            )
            _emit(result, json_out=json_out, out=out)
            append_run(result.run_record)
            _record_watch(result)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        sys.exit(EXIT_GENERIC)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(_classify_error(e))


def _run_compare(
    url: str,
    *,
    whisper_model: str,
    fresh: bool,
    json_out: bool,
    quiet: bool,
    out: Path | None,
) -> None:
    if not quiet:
        print("[compare] running local backend...", file=sys.stderr, flush=True)
    local_result = run_pipeline(
        url, backend_kind="local", whisper_model=whisper_model, fresh=fresh, quiet=quiet
    )
    append_run(local_result.run_record)

    if not quiet:
        print(
            "[compare] running cloud backend (transcript reused from cache)...",
            file=sys.stderr,
            flush=True,
        )
    cloud_result = run_pipeline(
        url, backend_kind="cloud", whisper_model=whisper_model, fresh=False, quiet=quiet
    )
    append_run(cloud_result.run_record)
    _record_watch(cloud_result)  # Record once (same video, just note the cloud run).

    # Always write both files for compare mode.
    out_dir = output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    local_path = out_dir / f"{local_result.slug}.local.md"
    cloud_path = out_dir / f"{cloud_result.slug}.cloud.md"

    local_md = render_markdown(
        local_result.summary,
        title=local_result.title,
        url=local_result.url,
        duration_str=duration_str(local_result.duration_seconds),
        backend_name="local (qwen2.5:7b)",
    )
    cloud_md = render_markdown(
        cloud_result.summary,
        title=cloud_result.title,
        url=cloud_result.url,
        duration_str=duration_str(cloud_result.duration_seconds),
        backend_name="cloud (claude-sonnet-4-6)",
    )
    write_markdown(local_path, local_md)
    write_markdown(cloud_path, cloud_md)

    if json_out:
        # Emit a comparison JSON object on stdout.
        import json as _json
        payload = {
            "url": url,
            "slug": local_result.slug,
            "title": local_result.title,
            "compare": {
                "local": _result_to_json_payload(local_result, str(local_path)),
                "cloud": _result_to_json_payload(cloud_result, str(cloud_path)),
            },
        }
        print(_json.dumps(payload, indent=2))
    else:
        print(f"wrote {local_path}", file=sys.stderr)
        print(f"wrote {cloud_path}", file=sys.stderr)
        # On stdout, emit a brief pointer for human use.
        print(f"local: {local_path}")
        print(f"cloud: {cloud_path}")


def _result_to_json_payload(result: PipelineResult, md_path: str) -> dict:
    return {
        "backend": result.backend_name,
        "summary": {
            "tldr": result.summary.tldr,
            "body": result.summary.body,
            "actionable_takeaways": result.summary.actionable_takeaways,
        },
        "stages": [
            {"name": s.name, "seconds": round(s.seconds, 3), **s.extra}
            for s in result.run_record.stages
        ],
        "total_seconds": round(result.run_record.total_seconds, 3),
        "estimated_cost_usd": round(result.run_record.estimated_cost_usd, 6),
        "paths": {"markdown": md_path},
    }


def _emit(result: PipelineResult, *, json_out: bool, out: Path | None) -> None:
    md = render_markdown(
        result.summary,
        title=result.title,
        url=result.url,
        duration_str=duration_str(result.duration_seconds),
        backend_name=f"{result.backend_name} ({result.run_record.llm_model})",
    )

    # Always also write the markdown file to summaries/ for posterity.
    out_path = out if out is not None else (output_dir() / f"{result.slug}.md")
    write_markdown(out_path, md)
    print(f"wrote {out_path}", file=sys.stderr)

    if json_out:
        payload = render_json(
            result.summary,
            url=result.url,
            slug=result.slug,
            title=result.title,
            duration_seconds=result.duration_seconds,
            backend_name=result.backend_name,
            run_record=result.run_record,
            paths={"markdown": str(out_path)},
        )
        print(payload)
    else:
        # When --out is given, stdout gets nothing (file is the contract).
        # When --out is not given, stdout gets the markdown so agents can pipe it.
        if out is None:
            print(md, end="")


@main.group()
def profile() -> None:
    """Manage your summarisation profile."""


@profile.command("init")
@click.option(
    "--linkedin-url",
    default=None,
    help="Public LinkedIn profile URL.",
)
@click.option(
    "--linkedin-pdf",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to your LinkedIn profile exported as PDF.",
)
@click.option(
    "--local",
    is_flag=True,
    help="Use local LLM instead of cloud to build profile.",
)
@click.option("--quiet", is_flag=True, help="Suppress progress on stderr.")
def profile_init(
    linkedin_url: str | None,
    linkedin_pdf: Path | None,
    local: bool,
    quiet: bool,
) -> None:
    """Build your summarisation profile from a LinkedIn URL or PDF fallback."""
    from .profile_builder import (
        build_profile_from_linkedin,
        build_profile_from_linkedin_url,
        save_profile,
    )

    if bool(linkedin_url) == bool(linkedin_pdf):
        print(
            "error: pass exactly one of --linkedin-url or --linkedin-pdf",
            file=sys.stderr,
        )
        sys.exit(EXIT_GENERIC)

    try:
        backend_kind = "local" if local else "cloud"
        if linkedin_url:
            profile_text = build_profile_from_linkedin_url(
                linkedin_url,
                backend_kind=backend_kind,
                quiet=quiet,
            )
        else:
            profile_text = build_profile_from_linkedin(
                linkedin_pdf,
                backend_kind=backend_kind,
                quiet=quiet,
            )
        path = save_profile(profile_text)
        if not quiet:
            print(f"\nProfile written to {path}", file=sys.stderr, flush=True)
            print("This will be used to personalise all future summaries.", file=sys.stderr)
            print("Edit the file freely — it's read live every run.\n", file=sys.stderr)
        # Also print the profile to stdout so the user can review it.
        print(path.read_text())
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(EXIT_GENERIC)


@profile.command("show")
def profile_show() -> None:
    """Show the current summarisation profile."""
    from .config import local_profile_path

    p = local_profile_path()
    if not p.exists():
        print(
            "No profile found. Run: vidsum profile init --linkedin-url <url>",
            file=sys.stderr,
        )
        sys.exit(EXIT_GENERIC)
    print(p.read_text())


def _record_watch(result: PipelineResult) -> None:
    """Best-effort append to watch history. Never fails the run."""
    try:
        from .profile_builder import append_watch_history

        append_watch_history(
            title=result.title,
            url=result.url,
            slug=result.slug,
            duration_seconds=result.duration_seconds,
            backend=result.backend_name,
        )
    except Exception:
        pass  # Profile may not exist yet — that's fine.


def _classify_error(e: Exception) -> int:
    msg = str(e).lower()
    if "url" in msg or "unsupported" in msg:
        return EXIT_BAD_URL
    if "yt-dlp" in msg or "download" in msg:
        return EXIT_DOWNLOAD
    if "whisper" in msg or "transcrib" in msg:
        return EXIT_TRANSCRIBE
    if "ollama" in msg or "anthropic" in msg or "json" in msg or "polish" in msg:
        return EXIT_LLM
    return EXIT_GENERIC
