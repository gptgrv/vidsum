from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from vidsum import cli
from vidsum.profile_builder import _extract_text_from_linkedin_html


def _write_profile(path: Path, text: str) -> Path:
    path.write_text(text)
    return path


def test_profile_init_accepts_linkedin_url(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    output_path = tmp_path / "profile.md"

    monkeypatch.setattr(
        "vidsum.profile_builder.build_profile_from_linkedin_url",
        lambda url, *, backend_kind, quiet: "## Professional identity\n\nBuilder",
    )
    monkeypatch.setattr(
        "vidsum.profile_builder.save_profile",
        lambda text, *, path=None: _write_profile(output_path, text),
    )

    result = runner.invoke(
        cli.main,
        ["profile", "init", "--linkedin-url", "https://www.linkedin.com/in/example/"],
    )

    assert result.exit_code == 0


def test_profile_init_requires_exactly_one_source() -> None:
    runner = CliRunner()

    result = runner.invoke(cli.main, ["profile", "init"])

    assert result.exit_code != 0
    assert "exactly one of --linkedin-url or --linkedin-pdf" in result.stderr


def test_extract_text_from_linkedin_html_prefers_structured_data() -> None:
    html = """
    <html>
      <head>
        <meta property="og:title" content="Ignored Title" />
        <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@type": "Person",
            "name": "Ada Lovelace",
            "jobTitle": "Product Leader",
            "description": "Building AI tools"
          }
        </script>
      </head>
    </html>
    """

    text = _extract_text_from_linkedin_html(html)

    assert "Ada Lovelace" in text
    assert "Product Leader" in text
