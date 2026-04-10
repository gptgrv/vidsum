from __future__ import annotations

from types import SimpleNamespace

from click.testing import CliRunner

from vidsum import cli


def test_summarize_uses_backend_from_environment(monkeypatch) -> None:
    runner = CliRunner()
    captured: dict[str, str] = {}

    monkeypatch.setenv("VIDSUM_BACKEND", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        cli,
        "run_pipeline",
        lambda url, *, backend_kind, whisper_model, fresh, quiet: captured.update(
            {
                "url": url,
                "backend_kind": backend_kind,
                "whisper_model": whisper_model,
            }
        )
        or SimpleNamespace(run_record=object()),
    )
    monkeypatch.setattr(cli, "_emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "append_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "_record_watch", lambda *args, **kwargs: None)

    result = runner.invoke(cli.main, ["summarize", "https://example.com/video"])

    assert result.exit_code == 0
    assert captured["url"] == "https://example.com/video"
    assert captured["backend_kind"] == "openai"


def test_explicit_cloud_flag_overrides_configured_backend(monkeypatch) -> None:
    runner = CliRunner()
    captured: dict[str, str] = {}

    monkeypatch.setenv("VIDSUM_BACKEND", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.setattr(
        cli,
        "run_pipeline",
        lambda url, *, backend_kind, whisper_model, fresh, quiet: captured.update(
            {"backend_kind": backend_kind}
        )
        or SimpleNamespace(run_record=object()),
    )
    monkeypatch.setattr(cli, "_emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "append_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "_record_watch", lambda *args, **kwargs: None)

    result = runner.invoke(cli.main, ["summarize", "--cloud", "https://example.com/video"])

    assert result.exit_code == 0
    assert captured["backend_kind"] == "cloud"
