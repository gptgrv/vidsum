"""One-time profile builder from LinkedIn profile data + watch history refinement.

Workflow:
  1. User provides a LinkedIn URL or PDF.
  2. We extract text, send it to the LLM, and produce a structured profile.md.
  3. After each summary run, we append to the watch history section.
  4. The profile is read live every run (via profile.py).
"""

from __future__ import annotations

import json
import re
import sys
from html import unescape
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import local_profile_path


def _load_build_profile_prompt() -> str:
    return (Path(__file__).parent / "prompts" / "build_profile.md").read_text()


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract text from a PDF. Uses pdfplumber if available, falls back to PyPDF2."""
    try:
        import pdfplumber

        with pdfplumber.open(pdf_path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n\n".join(pages).strip()
    except ImportError:
        pass

    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(str(pdf_path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages).strip()
    except ImportError:
        pass

    raise RuntimeError(
        "No PDF reader available. Install pdfplumber:\n  uv add pdfplumber"
    )


def fetch_linkedin_url_text(url: str) -> str:
    """Fetch and extract readable text from a public LinkedIn profile URL."""
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    )

    try:
        with urlopen(request, timeout=20) as response:
            html = response.read().decode("utf-8", errors="ignore")
    except HTTPError as exc:
        raise RuntimeError(f"LinkedIn returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not fetch LinkedIn URL: {exc.reason}") from exc

    text = _extract_text_from_linkedin_html(html)
    if not text:
        raise RuntimeError("No usable profile text found at the LinkedIn URL")
    return text


def _extract_text_from_linkedin_html(html: str) -> str:
    """Best-effort extraction from public LinkedIn HTML."""
    pieces: list[str] = []

    for match in re.findall(
        r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    ):
        try:
            data = json.loads(unescape(match))
        except json.JSONDecodeError:
            continue
        pieces.extend(_flatten_text(data))

    meta_patterns = [
        r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"',
        r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"',
        r'<meta[^>]+name="description"[^>]+content="([^"]+)"',
    ]
    for pattern in meta_patterns:
        pieces.extend(re.findall(pattern, html, flags=re.IGNORECASE))

    if not pieces:
        body = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
        body = re.sub(r"(?is)<style.*?>.*?</style>", " ", body)
        body = re.sub(r"(?s)<[^>]+>", " ", body)
        pieces.append(body)

    cleaned = []
    for piece in pieces:
        piece = unescape(piece)
        piece = re.sub(r"\s+", " ", piece).strip()
        if piece and piece not in cleaned:
            cleaned.append(piece)

    return "\n".join(cleaned[:40]).strip()


def _flatten_text(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            items.extend(_flatten_text(item))
        return items
    if isinstance(value, dict):
        items = []
        for item in value.values():
            items.extend(_flatten_text(item))
        return items
    return []


def build_profile_from_linkedin(
    pdf_path: Path,
    *,
    backend_kind: str = "cloud",
    model: str | None = None,
    quiet: bool = False,
) -> str:
    """Extract LinkedIn PDF text, send to LLM, return a structured profile."""
    from .backends import make_backend

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    if not quiet:
        print(f"  reading PDF: {pdf_path}", file=sys.stderr, flush=True)

    linkedin_text = extract_pdf_text(pdf_path)
    if not linkedin_text.strip():
        raise RuntimeError(f"No text extracted from {pdf_path}. Is this a valid LinkedIn PDF?")

    if not quiet:
        print(
            f"  extracted {len(linkedin_text)} chars from PDF",
            file=sys.stderr,
            flush=True,
        )

    backend = make_backend(backend_kind, model=model)
    system = _load_build_profile_prompt()
    user = f"# LinkedIn profile content\n\n{linkedin_text}"

    if not quiet:
        print(f"  building profile via {backend.name}...", file=sys.stderr, flush=True)

    result = backend.complete(system, user, max_tokens=2048)
    return result.text.strip()


def build_profile_from_linkedin_url(
    url: str,
    *,
    backend_kind: str = "cloud",
    model: str | None = None,
    quiet: bool = False,
) -> str:
    """Fetch LinkedIn URL text, send to LLM, return a structured profile."""
    from .backends import make_backend

    if not quiet:
        print(f"  fetching LinkedIn URL: {url}", file=sys.stderr, flush=True)

    linkedin_text = fetch_linkedin_url_text(url)
    if not quiet:
        print(
            f"  extracted {len(linkedin_text)} chars from LinkedIn URL",
            file=sys.stderr,
            flush=True,
        )

    backend = make_backend(backend_kind, model=model)
    system = _load_build_profile_prompt()
    user = f"# LinkedIn profile content\n\n{linkedin_text}"

    if not quiet:
        print(f"  building profile via {backend.name}...", file=sys.stderr, flush=True)

    result = backend.complete(system, user, max_tokens=2048)
    return result.text.strip()


def save_profile(profile_text: str, *, path: Path | None = None) -> Path:
    """Write the profile to disk with the standard header."""
    p = path or local_profile_path()
    header = (
        "# Summarisation Profile\n"
        "#\n"
        f"# Built from LinkedIn on {datetime.now(UTC).strftime('%Y-%m-%d')}\n"
        "# This file is read live every run. Edit freely.\n"
        "# Watch history is appended automatically after each summary.\n\n"
    )
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(header + profile_text + "\n\n---\n\n## Watch history\n\n")
    return p


def append_watch_history(
    *,
    title: str,
    url: str,
    slug: str,
    duration_seconds: float,
    backend: str,
) -> None:
    """Append a video to the watch history section of profile.md."""
    p = local_profile_path()
    if not p.exists():
        return  # No profile yet — nothing to append to.

    date = datetime.now(UTC).strftime("%Y-%m-%d")
    dur_min = int(duration_seconds / 60)
    entry = f"- [{title}]({url}) — {dur_min}min, {backend} ({date})\n"

    content = p.read_text()
    # Append to the end (watch history is the last section).
    p.write_text(content + entry)
