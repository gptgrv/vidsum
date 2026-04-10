"""Timing instrumentation and runs.jsonl writer."""

from __future__ import annotations

import json
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime

from .config import runs_log_path
from .types import RunRecord, StageTiming


@contextmanager
def stage(name: str, timings: list[StageTiming], *, quiet: bool = False):
    """Context manager that times a stage and prints progress to stderr."""
    if not quiet:
        print(f"[{name}] starting...", file=sys.stderr, flush=True)
    t0 = time.monotonic()
    extra: dict = {}
    try:
        yield extra
    finally:
        elapsed = time.monotonic() - t0
        timings.append(StageTiming(name=name, seconds=elapsed, extra=dict(extra)))
        if not quiet:
            extra_str = ""
            if extra:
                extra_str = " " + " ".join(f"{k}={v}" for k, v in extra.items())
            print(f"[{name}] done in {elapsed:.1f}s{extra_str}", file=sys.stderr, flush=True)


def append_run(record: RunRecord) -> None:
    """Append a run record to runs.jsonl."""
    path = runs_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    obj = {
        "run_id": record.run_id,
        "url": record.url,
        "slug": record.slug,
        "title": record.title,
        "duration_seconds": record.duration_seconds,
        "backend": record.backend,
        "whisper_model": record.whisper_model,
        "llm_model": record.llm_model,
        "total_seconds": record.total_seconds,
        "estimated_cost_usd": record.estimated_cost_usd,
        "timestamp": record.timestamp,
        "stages": [
            {"name": s.name, "seconds": round(s.seconds, 3), **s.extra}
            for s in record.stages
        ],
    }
    with path.open("a") as f:
        f.write(json.dumps(obj) + "\n")


def make_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
