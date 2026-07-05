"""Optional Hugging Face endpoint adapter (TGI / Inference Endpoints).

Uses the OpenAI-compatible chat route that TGI and HF endpoints expose.
A token is applied only if configured — the platform never requires one.
"""
from __future__ import annotations

from ..config import ModelConfig
from .openai_compat import OpenAICompatProvider


class HFEndpointProvider(OpenAICompatProvider):
    name = "hf_endpoint"

    def __init__(self, cfg: ModelConfig):
        super().__init__(cfg)
