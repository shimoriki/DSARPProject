"""Native Ollama /api/chat provider."""
from __future__ import annotations

import time

import httpx

from ..config import ModelConfig
from .base import ChatResult, ProviderError, estimate_tokens


class OllamaProvider:
    name = "ollama"

    def __init__(self, cfg: ModelConfig):
        self.cfg = cfg
        self.model_id = cfg.model_id
        self.base_url = cfg.base_url.rstrip("/")

    def chat(self, system: str, user: str, *, temperature: float | None = None,
             max_tokens: int | None = None) -> ChatResult:
        payload = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {
                "temperature": temperature if temperature is not None else self.cfg.temperature,
                "num_predict": max_tokens or self.cfg.max_tokens,
            },
        }
        start = time.perf_counter()
        try:
            resp = httpx.post(f"{self.base_url}/api/chat", json=payload,
                              timeout=self.cfg.timeout_seconds)
            resp.raise_for_status()
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"Ollama server is not reachable at {self.base_url}. "
                "Install Ollama (https://ollama.com) and start it with "
                "'ollama serve' (or the desktop app), or switch the provider "
                "to 'mock' in config/config.yaml to work offline.") from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise ProviderError(
                    f"Model '{self.model_id}' is not available in Ollama. "
                    f"Pull it first:  ollama pull {self.model_id}") from exc
            raise ProviderError(f"ollama request failed: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"ollama request failed: {exc}") from exc
        elapsed = time.perf_counter() - start
        data = resp.json()
        text = (data.get("message") or {}).get("content", "")
        prompt_tokens = data.get("prompt_eval_count") or estimate_tokens(system + user)
        completion_tokens = data.get("eval_count") or estimate_tokens(text)
        return ChatResult(
            text=text, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            runtime_seconds=round(elapsed, 3), raw=data)
