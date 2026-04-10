"""Local backend via Ollama. Default model: qwen2.5:7b."""

from __future__ import annotations

from . import LLMResult

# Ollama defaults num_ctx to 2048 tokens, which silently truncates anything
# longer. We need to fit: profile (~1.5k) + system + user content (transcript
# up to 12k) or rolling summary (~6k) + response (up to ~12k). 24k gives
# headroom on all of those.
# Memory cost on Qwen 2.5 7B (Q4) with KV cache: well under 1 GB extra.
LOCAL_NUM_CTX = 24000


class LocalBackend:
    name = "local"

    def __init__(self, model: str):
        self.model = model

    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> LLMResult:
        import ollama

        resp = ollama.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            options={
                "num_ctx": LOCAL_NUM_CTX,
                "num_predict": max_tokens,
                "temperature": 0.3,
            },
        )
        text = resp["message"]["content"]
        input_tokens = int(resp.get("prompt_eval_count") or 0)
        output_tokens = int(resp.get("eval_count") or 0)
        return LLMResult(text=text, input_tokens=input_tokens, output_tokens=output_tokens)
