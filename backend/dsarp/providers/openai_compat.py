"""OpenAI-compatible chat provider: vLLM, llama.cpp server, LM Studio, etc."""
from __future__ import annotations

import time

import httpx

from ..config import ModelConfig
from .base import ChatResult, ProviderError, estimate_tokens


class OpenAICompatProvider:
    name = "openai_compat"

    def __init__(self, cfg: ModelConfig):
        self.cfg = cfg
        self.model_id = cfg.model_id
        base = cfg.base_url.rstrip("/")
        self.url = base + ("/chat/completions" if base.endswith("/v1")
                           else "/v1/chat/completions")

    def chat(self, system: str, user: str, *, temperature: float | None = None,
             max_tokens: int | None = None) -> ChatResult:
        headers = {"Content-Type": "application/json"}
        if self.cfg.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.api_key}"
        payload = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature if temperature is not None else self.cfg.temperature,
            "max_tokens": max_tokens or self.cfg.max_tokens,
        }
        start = time.perf_counter()
        try:
            resp = httpx.post(self.url, json=payload, headers=headers,
                              timeout=self.cfg.timeout_seconds)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"openai-compatible request failed: {exc}") from exc
        elapsed = time.perf_counter() - start
        data = resp.json()
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as exc:
            raise ProviderError(f"unexpected response shape: {data}") from exc
        usage = data.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens") or estimate_tokens(system + user)
        completion_tokens = usage.get("completion_tokens") or estimate_tokens(text)
        return ChatResult(
            text=text, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            total_tokens=usage.get("total_tokens") or prompt_tokens + completion_tokens,
            runtime_seconds=round(elapsed, 3), raw=data)
