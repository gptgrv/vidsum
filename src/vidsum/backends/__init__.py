"""Backend protocol + factory.

A backend is anything that can take a system prompt + user prompt and return text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..config import DEFAULT_CLOUD_MODEL, DEFAULT_LOCAL_MODEL, DEFAULT_OPENAI_MODEL


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int


class Backend(Protocol):
    name: str
    model: str

    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> LLMResult: ...


def make_backend(kind: str, *, model: str | None = None) -> Backend:
    if kind == "local":
        from .local import LocalBackend
        return LocalBackend(model=model or DEFAULT_LOCAL_MODEL)
    if kind == "cloud":
        from .cloud import CloudBackend
        return CloudBackend(model=model or DEFAULT_CLOUD_MODEL)
    if kind == "openai":
        from .openai import OpenAIBackend
        return OpenAIBackend(model=model or DEFAULT_OPENAI_MODEL)
    raise ValueError(f"unknown backend kind: {kind!r}")
