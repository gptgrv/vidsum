"""Output serializers: markdown (primary) and JSON (agent contract)."""

from __future__ import annotations

import json
from pathlib import Path

from .types import RunRecord, Summary


def render_markdown(
    summary: Summary, *, title: str, url: str, duration_str: str, backend_name: str
) -> str:
    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"*Source:* {url}  ")
    lines.append(f"*Duration:* {duration_str}  ")
    lines.append(f"*Summarised by:* `{backend_name}`")
    lines.append("")
    lines.append("## TL;DR")
    lines.append("")
    lines.append(summary.tldr.strip() or "_(no TL;DR returned)_")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(summary.body.strip() or "_(no body returned)_")
    lines.append("")
    if summary.actionable_takeaways:
        lines.append("---")
        lines.append("")
        lines.append("## Actionable takeaways")
        lines.append("")
        for a in summary.actionable_takeaways:
            a = a.strip()
            if a:
                lines.append(f"- {a}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_json(
    summary: Summary,
    *,
    url: str,
    slug: str,
    title: str,
    duration_seconds: float,
    backend_name: str,
    run_record: RunRecord | None,
    paths: dict,
) -> str:
    obj = {
        "url": url,
        "slug": slug,
        "title": title,
        "duration_seconds": duration_seconds,
        "backend": backend_name,
        "summary": {
            "tldr": summary.tldr,
            "body": summary.body,
            "actionable_takeaways": summary.actionable_takeaways,
        },
        "paths": paths,
    }
    if run_record:
        obj["stages"] = [
            {"name": s.name, "seconds": round(s.seconds, 3), **s.extra}
            for s in run_record.stages
        ]
        obj["total_seconds"] = round(run_record.total_seconds, 3)
        obj["estimated_cost_usd"] = round(run_record.estimated_cost_usd, 6)
    return json.dumps(obj, indent=2)


def write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
