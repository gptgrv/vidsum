"""Interactive onboarding flow for vidsum.

Supports two modes:
- Interactive (human): colorful prompts, step-by-step guidance
- Non-interactive (agent): all config via flags, no prompts
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.theme import Theme

# ── Theme ────────────────────────────────────────────────────────────────
# Cyan/teal accent, green for success, yellow for warnings, dim for secondary text.
THEME = Theme(
    {
        "accent": "bold cyan",
        "success": "bold green",
        "warn": "bold yellow",
        "err": "bold red",
        "dim": "dim white",
        "step": "bold bright_cyan",
        "prompt": "bold white",
        "brand": "bold bright_cyan",
    }
)

console = Console(theme=THEME, stderr=True)

# ── Dotenv helpers ───────────────────────────────────────────────────────

ENV_PATH = Path(".env")


def _read_env() -> dict[str, str]:
    """Read existing .env into a dict (simple key=value, no interpolation)."""
    if not ENV_PATH.exists():
        return {}
    pairs: dict[str, str] = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            pairs[k.strip()] = v.strip().strip("\"'")
    return pairs


def _write_env(pairs: dict[str, str]) -> None:
    """Write dict back to .env, preserving comments and unrecognised lines."""
    lines: list[str] = []
    seen: set[str] = set()

    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, _, _ = stripped.partition("=")
                k = k.strip()
                if k in pairs:
                    lines.append(f"{k}={pairs[k]}")
                    seen.add(k)
                    continue
            lines.append(line)

    for k, v in pairs.items():
        if k not in seen:
            lines.append(f"{k}={v}")

    ENV_PATH.write_text("\n".join(lines) + "\n")


# ── Banner ───────────────────────────────────────────────────────────────


def _banner() -> None:
    title = Text()
    title.append("  vidsum", style="bold bright_cyan")
    title.append("  onboarding", style="dim white")

    console.print()
    console.print(
        Panel(
            Text.from_markup(
                "[bold bright_cyan]Personalised video & audio summaries.[/]\n"
                "[dim]Let's get you set up in under a minute.[/]"
            ),
            title=title,
            border_style="cyan",
            padding=(1, 3),
        )
    )
    console.print()


# ── Step 1: Backend ─────────────────────────────────────────────────────

BACKENDS = [
    ("local", "Ollama", "Free, private, runs on your machine (~5 GB RAM)"),
    ("cloud", "Anthropic Claude", "Claude Sonnet 4.6 — high quality, needs API key"),
    ("openai", "OpenAI", "GPT-4o — high quality, needs API key"),
]


def _choose_backend_interactive() -> str:
    console.print("[step]Step 1[/]  [prompt]Choose your LLM backend[/]\n")

    for i, (key, name, desc) in enumerate(BACKENDS, 1):
        num = Text(f"  [{i}] ", style="accent")
        label = Text(f"{name}", style="bold white")
        detail = Text(f"  {desc}", style="dim")
        console.print(num, label, detail, sep="")

    console.print()
    while True:
        choice = console.input("[accent]  ▸ Pick a number (1/2/3): [/]").strip()
        if choice in ("1", "2", "3"):
            backend = BACKENDS[int(choice) - 1][0]
            console.print(f"  [success]✓[/] [dim]{BACKENDS[int(choice) - 1][1]}[/]\n")
            return backend
        console.print("  [warn]Enter 1, 2, or 3.[/]")


# ── Step 2: Configure backend ───────────────────────────────────────────


def _configure_local_interactive() -> dict[str, str]:
    """Check Ollama is available, offer to pull the default model."""
    from .config import DEFAULT_LOCAL_MODEL

    console.print("[step]Step 2[/]  [prompt]Configure local backend[/]\n")

    # Check ollama binary
    if not shutil.which("ollama"):
        console.print("  [err]✗[/] [bold]ollama[/] not found on PATH.")
        console.print("  [dim]Install from https://ollama.com then re-run.[/]\n")
        sys.exit(1)

    # Check ollama is running
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            console.print("  [err]✗[/] ollama is installed but not running.")
            console.print("  [dim]Start it with: ollama serve[/]\n")
            sys.exit(1)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        console.print("  [err]✗[/] Could not reach ollama.")
        console.print("  [dim]Start it with: ollama serve[/]\n")
        sys.exit(1)

    console.print("  [success]✓[/] [dim]ollama is running[/]")

    # Check if default model is pulled
    model = DEFAULT_LOCAL_MODEL
    model_input = console.input(
        f"  [accent]▸ Model [{model}]: [/]"
    ).strip()
    if model_input:
        model = model_input

    available = subprocess.run(
        ["ollama", "list"], capture_output=True, text=True, timeout=10
    )
    if model.split(":")[0] not in available.stdout:
        console.print(f"  [dim]Pulling {model}... this may take a few minutes.[/]")
        pull = subprocess.run(["ollama", "pull", model], timeout=600)
        if pull.returncode != 0:
            console.print(f"  [err]✗[/] Failed to pull {model}.")
            sys.exit(1)

    console.print(f"  [success]✓[/] [dim]Model ready: {model}[/]\n")
    return {"VIDSUM_BACKEND": "local", "VIDSUM_MODEL": model}


def _configure_cloud_interactive(backend: str) -> dict[str, str]:
    """Prompt for API key and model, with privacy reassurance."""
    from .config import DEFAULT_CLOUD_MODEL, DEFAULT_OPENAI_MODEL

    is_openai = backend == "openai"
    provider = "OpenAI" if is_openai else "Anthropic"
    key_name = "OPENAI_API_KEY" if is_openai else "ANTHROPIC_API_KEY"
    default_model = DEFAULT_OPENAI_MODEL if is_openai else DEFAULT_CLOUD_MODEL
    key_url = "platform.openai.com/api-keys" if is_openai else "console.anthropic.com"

    console.print(f"[step]Step 2[/]  [prompt]Configure {provider} backend[/]\n")
    console.print(
        f"  [dim]Your key is stored in [bold].env[/bold] and never leaves your device[/]\n"
        f"  [dim]except when making API calls to {provider}.[/]"
    )
    console.print(f"  [dim]Get a key from {key_url}[/]\n")

    # Check if key already exists in env
    existing = os.environ.get(key_name) or _read_env().get(key_name)
    if existing:
        masked = existing[:8] + "..." + existing[-4:]
        use_existing = console.input(
            f"  [accent]▸ Found existing key ({masked}). Keep it? [Y/n]: [/]"
        ).strip().lower()
        if use_existing in ("", "y", "yes"):
            api_key = existing
            console.print("  [success]✓[/] [dim]Using existing key[/]")
        else:
            api_key = console.input(f"  [accent]▸ {provider} API key: [/]").strip()
    else:
        api_key = console.input(f"  [accent]▸ {provider} API key: [/]").strip()

    if not api_key:
        console.print(f"  [err]✗[/] API key is required for {provider} backend.")
        sys.exit(1)

    model = console.input(
        f"  [accent]▸ Model [{default_model}]: [/]"
    ).strip() or default_model

    console.print(f"  [success]✓[/] [dim]Saved to .env[/]\n")
    return {key_name: api_key, "VIDSUM_BACKEND": backend, "VIDSUM_MODEL": model}


# ── Step 3: Profile ─────────────────────────────────────────────────────


def _profile_interactive(env_pairs: dict[str, str]) -> None:
    """Optionally set up a profile from LinkedIn URL or PDF."""
    console.print("[step]Step 3[/]  [prompt]Personalisation[/] [dim](optional)[/]\n")
    console.print(
        "  [dim]A profile makes summaries smarter — it tells vidsum what you[/]\n"
        "  [dim]already know and what to emphasise. You can skip this for now.[/]"
    )
    console.print()

    source = console.input(
        "  [accent]▸ LinkedIn profile URL (or Enter to skip): [/]"
    ).strip()

    if not source:
        console.print("  [dim]Skipped — you can set this up later with:[/]")
        console.print("  [dim]  vidsum onboard --linkedin-url <url>[/]")
        console.print("  [dim]  vidsum profile init --linkedin-pdf ~/Downloads/Profile.pdf[/]\n")
        return

    # Determine if it's a URL or a file path
    if source.startswith("http"):
        _build_profile_from_url(source, env_pairs)
    elif Path(source).expanduser().exists():
        _build_profile_from_pdf(Path(source).expanduser(), env_pairs)
    else:
        console.print("  [warn]Doesn't look like a URL or existing file path.[/]")
        console.print("  [dim]Skipping profile — set it up later with:[/]")
        console.print("  [dim]  vidsum onboard --linkedin-url <url>[/]")
        console.print("  [dim]  vidsum profile init --linkedin-pdf ~/Downloads/Profile.pdf[/]\n")


def _build_profile_from_url(url: str, env_pairs: dict[str, str]) -> None:
    """Try scraping LinkedIn profile from URL."""
    console.print("  [dim]Fetching LinkedIn profile...[/]")

    try:
        from .profile_builder import build_profile_from_linkedin_url, save_profile

        # Determine backend from what was just configured
        backend_kind = env_pairs.get("VIDSUM_BACKEND", "cloud")
        # Temporarily set env vars so the backend can find keys
        for k, v in env_pairs.items():
            os.environ[k] = v

        profile_text = build_profile_from_linkedin_url(
            url, backend_kind=backend_kind, quiet=True
        )
        path = save_profile(profile_text)
        console.print(f"  [success]✓[/] [dim]Profile written to {path}[/]\n")
    except Exception as e:
        msg = str(e).lower()
        if "block" in msg or "403" in msg or "captcha" in msg or "denied" in msg:
            console.print(
                "  [warn]LinkedIn blocked the request.[/]\n"
                "  [dim]This happens — LinkedIn restricts automated access.[/]"
            )
        else:
            console.print(f"  [warn]Could not fetch profile: {e}[/]")

        console.print(
            "  [dim]Fallback: download your LinkedIn PDF and run:[/]\n"
            "  [dim]  vidsum profile init --linkedin-pdf ~/Downloads/Profile.pdf[/]\n"
        )


def _build_profile_from_pdf(pdf_path: Path, env_pairs: dict[str, str]) -> None:
    """Build profile from a local LinkedIn PDF."""
    console.print("  [dim]Building profile from PDF...[/]")

    try:
        from .profile_builder import build_profile_from_linkedin, save_profile

        backend_kind = env_pairs.get("VIDSUM_BACKEND", "cloud")
        for k, v in env_pairs.items():
            os.environ[k] = v

        profile_text = build_profile_from_linkedin(
            pdf_path, backend_kind=backend_kind, quiet=True
        )
        path = save_profile(profile_text)
        console.print(f"  [success]✓[/] [dim]Profile written to {path}[/]\n")
    except Exception as e:
        console.print(f"  [warn]Could not build profile: {e}[/]")
        console.print("  [dim]You can try again later with:[/]")
        console.print(f"  [dim]  vidsum profile init --linkedin-pdf {pdf_path}[/]\n")


# ── Finish ───────────────────────────────────────────────────────────────


def _finish() -> None:
    console.print(
        Panel(
            Text.from_markup(
                "[bold bright_cyan]You're all set![/]\n\n"
                "[dim]Try it out:[/]\n"
                "  [bold white]vidsum \"https://youtube.com/watch?v=...\"[/]\n\n"
                "[dim]Other commands:[/]\n"
                "  [bold white]vidsum status[/]          [dim]— check your setup[/]\n"
                "  [bold white]vidsum profile show[/]    [dim]— view your profile[/]\n"
                "  [bold white]vidsum --help[/]          [dim]— all options[/]"
            ),
            border_style="green",
            padding=(1, 3),
        )
    )
    console.print()


# ── Main entry points ───────────────────────────────────────────────────


def run_onboard_interactive() -> None:
    """Full interactive onboarding flow."""
    _banner()

    backend = _choose_backend_interactive()

    if backend == "local":
        env_pairs = _configure_local_interactive()
    else:
        env_pairs = _configure_cloud_interactive(backend)

    # Save to .env before profile step (profile build needs the keys)
    _write_env(env_pairs)

    _profile_interactive(env_pairs)
    _finish()


def run_onboard_noninteractive(
    *,
    backend: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    linkedin_url: str | None = None,
    linkedin_pdf: Path | None = None,
) -> None:
    """Non-interactive onboarding for agents. All config via arguments."""
    from .config import DEFAULT_CLOUD_MODEL, DEFAULT_LOCAL_MODEL, DEFAULT_OPENAI_MODEL

    env_pairs: dict[str, str] = {}

    if backend:
        env_pairs["VIDSUM_BACKEND"] = backend

        if backend == "local":
            env_pairs["VIDSUM_MODEL"] = model or DEFAULT_LOCAL_MODEL
        elif backend == "cloud":
            if not api_key:
                api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                print("error: --api-key required for cloud backend", file=sys.stderr)
                sys.exit(1)
            env_pairs["ANTHROPIC_API_KEY"] = api_key
            env_pairs["VIDSUM_MODEL"] = model or DEFAULT_CLOUD_MODEL
        elif backend == "openai":
            if not api_key:
                api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                print("error: --api-key required for openai backend", file=sys.stderr)
                sys.exit(1)
            env_pairs["OPENAI_API_KEY"] = api_key
            env_pairs["VIDSUM_MODEL"] = model or DEFAULT_OPENAI_MODEL

    if env_pairs:
        _write_env(env_pairs)
        print(f"wrote {ENV_PATH}", file=sys.stderr)

    # Profile setup
    if linkedin_url:
        for k, v in env_pairs.items():
            os.environ[k] = v
        try:
            from .profile_builder import build_profile_from_linkedin_url, save_profile

            bk = env_pairs.get("VIDSUM_BACKEND", "cloud")
            text = build_profile_from_linkedin_url(linkedin_url, backend_kind=bk, quiet=True)
            path = save_profile(text)
            print(f"wrote {path}", file=sys.stderr)
        except Exception as e:
            print(f"error: linkedin url failed: {e}", file=sys.stderr)
            print("fallback: use --linkedin-pdf instead", file=sys.stderr)
            sys.exit(1)

    if linkedin_pdf:
        for k, v in env_pairs.items():
            os.environ[k] = v
        try:
            from .profile_builder import build_profile_from_linkedin, save_profile

            bk = env_pairs.get("VIDSUM_BACKEND", "cloud")
            text = build_profile_from_linkedin(linkedin_pdf, backend_kind=bk, quiet=True)
            path = save_profile(text)
            print(f"wrote {path}", file=sys.stderr)
        except Exception as e:
            print(f"error: profile build failed: {e}", file=sys.stderr)
            sys.exit(1)


# ── Status ───────────────────────────────────────────────────────────────


def show_status() -> None:
    """Print current configuration status."""
    from .config import local_profile_path

    env = _read_env()

    console.print()
    console.print(
        Panel(
            Text.from_markup("[bold bright_cyan]vidsum status[/]"),
            border_style="cyan",
            padding=(0, 3),
        )
    )
    console.print()

    # Backend
    backend = env.get("VIDSUM_BACKEND", os.environ.get("VIDSUM_BACKEND", ""))
    model = env.get("VIDSUM_MODEL", os.environ.get("VIDSUM_MODEL", ""))
    if backend:
        console.print(f"  [success]✓[/] Backend:  [bold]{backend}[/] [dim]({model or 'default'})[/]")
    else:
        console.print("  [warn]○[/] Backend:  [dim]not configured — run vidsum onboard[/]")

    # API keys
    has_anthropic = bool(env.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))
    has_openai = bool(env.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY"))
    if has_anthropic:
        console.print("  [success]✓[/] Anthropic: [dim]key configured[/]")
    if has_openai:
        console.print("  [success]✓[/] OpenAI:    [dim]key configured[/]")
    if not has_anthropic and not has_openai and backend != "local":
        console.print("  [warn]○[/] API key:  [dim]not configured[/]")

    # Ollama
    if backend == "local" or not backend:
        has_ollama = bool(shutil.which("ollama"))
        if has_ollama:
            console.print("  [success]✓[/] Ollama:    [dim]installed[/]")
        else:
            console.print("  [warn]○[/] Ollama:    [dim]not found[/]")

    # Profile
    profile = local_profile_path()
    if profile.exists():
        lines = len(profile.read_text().splitlines())
        console.print(f"  [success]✓[/] Profile:   [dim]{profile} ({lines} lines)[/]")
    else:
        console.print("  [warn]○[/] Profile:   [dim]not set up[/]")

    # .env
    if ENV_PATH.exists():
        console.print(f"  [success]✓[/] Config:    [dim]{ENV_PATH.resolve()}[/]")
    else:
        console.print("  [warn]○[/] Config:    [dim]no .env file[/]")

    console.print()
