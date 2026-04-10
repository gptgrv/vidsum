"""Cloud backend via Anthropic. Default model: claude-sonnet-4-6."""

from __future__ import annotations

import os

from . import LLMResult


class CloudBackend:
    name = "cloud"

    def __init__(self, model: str):
        self.model = model
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set; cloud backend requires it. "
                "Get a key from console.anthropic.com and export it."
            )

    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> LLMResult:
        import anthropic

        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        return LLMResult(
            text=text,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )
