"""Local model provider abstraction.

Supported: Ollama (native API), any OpenAI-compatible endpoint (vLLM,
llama.cpp server, LM Studio), an optional Hugging Face endpoint (token
optional), and a deterministic offline mock for tests/demo. The platform
never requires a cloud API or a Hugging Face token.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..config import ModelConfig


class ProviderError(RuntimeError):
    pass


@dataclass
class ChatResult:
    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    runtime_seconds: float = 0.0
    raw: dict = field(default_factory=dict)


class ModelProvider(Protocol):
    name: str
    model_id: str

    def chat(self, system: str, user: str, *, temperature: float | None = None,
             max_tokens: int | None = None) -> ChatResult: ...


def make_provider(cfg: ModelConfig) -> "ModelProvider":
    provider = (cfg.provider or "mock").lower()
    if provider == "ollama":
        from .ollama import OllamaProvider
        return OllamaProvider(cfg)
    if provider in ("openai_compat", "vllm", "llamacpp", "llama_cpp", "lmstudio"):
        from .openai_compat import OpenAICompatProvider
        return OpenAICompatProvider(cfg)
    if provider == "hf_endpoint":
        from .hf_endpoint import HFEndpointProvider
        return HFEndpointProvider(cfg)
    if provider == "mock":
        from .mock import MockProvider
        return MockProvider(cfg)
    raise ProviderError(f"unknown model provider '{cfg.provider}'")


def estimate_tokens(text: str) -> int:
    """Rough fallback when an endpoint reports no usage (≈4 chars/token)."""
    return max(1, len(text) // 4)
