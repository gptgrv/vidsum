"""OpenAI backend. Default model: gpt-4o."""

from __future__ import annotations

import os

from . import LLMResult


class OpenAIBackend:
    name = "openai"

    def __init__(self, model: str):
        self.model = model
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError(
                "OPENAI_API_KEY not set; OpenAI backend requires it. "
                "Get a key from platform.openai.com and export it."
            )

    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> LLMResult:
        import openai

        client = openai.OpenAI()
        resp = client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=0.3,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        text = resp.choices[0].message.content or ""
        usage = resp.usage
        return LLMResult(
            text=text,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )
