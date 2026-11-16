"""Local model access for DSARP.

One OpenAI-compatible client covers every way you can serve a model on this machine —
Ollama, vLLM, llama.cpp's server, LM Studio all expose `/v1/chat/completions`. The model
NAME is the only thing that changes between them, so nothing here is Nemotron-specific:
point `base_url` at the server and `model` at whatever tag it serves.

The interface is whatever `refactoring/ai_recipes.propose()` already duck-types on:

    provider.generate(prompt, max_tokens=..., temperature=..., json_mode=...) -> .text

Nothing more. Kept deliberately small — a provider that can also stream, count tokens or
retry is a provider with three more ways to be wrong at 3am. The one exception: HTTP 429 is
retried with backoff, because hosted free tiers rate-limit and a lost call reads as a weak model.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Optional, Protocol

# Ollama's default port. vLLM serves 8000, llama.cpp 8080 — override via config/--base-url.
DEFAULT_BASE_URL = "http://localhost:11434"


@dataclass
class Completion:
    text: str
    model: str = ""
    # Real counts from the server's usage block when it reports them. The budget log
    # distinguishes these from its own estimates, so None must stay None rather than 0.
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    raw: Optional[Dict[str, Any]] = None


class ModelProvider(Protocol):
    """The whole interface. agents/explainer.py, refactoring/ai_recipes.py and
    agents/spoon_refactor.py all duck-type on exactly this."""

    name: str
    model: str

    def generate(self, prompt: str, **kwargs: Any) -> Completion: ...


class OfflineProvider:
    """No model configured — the laptop default. Returns nothing rather than failing, so
    the evidence pipeline still produces schema-valid output with an empty explanation."""

    name = model = "offline"

    def generate(self, prompt: str, **_: Any) -> Completion:
        return Completion(text="", model=self.model)


class LocalProvider:
    """Any OpenAI-compatible endpoint served from this machine."""

    def __init__(self, model: str, base_url: str = DEFAULT_BASE_URL,
                 timeout: int = 300, system: str = "", api_key: str = "dsarp-local",
                 retries: int = 6, uncapped: bool = False, min_interval: float = 0,
                 max_wait: float = 300):
        self.model = model
        self.name = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.system = system
        self.api_key = api_key
        # Hosted free tiers answer 429 when their shared pool is busy; a call that gave up at
        # once read as a model that could not plan (Gemma 4 on OpenRouter, 0 rounds of 3).
        self.retries = retries
        # Reasoning models spend hidden tokens before the answer: Cohere's code model used all
        # 800 thinking and returned nothing. Uncapped leaves the limit to the server's capacity.
        self.uncapped = uncapped
        # Throttle: at least this many seconds between calls, so a per-minute limit is never hit.
        self.min_interval = min_interval
        # A 429 whose reset is further off than this is a spent quota (daily cap), not a busy
        # pool: fail at once with the reset time instead of sleeping for hours.
        self.max_wait = max_wait
        self._last_call = None

    def _throttle(self) -> None:
        if self.min_interval and self._last_call is not None:
            gap = self.min_interval - (time.monotonic() - self._last_call)
            if gap > 0:
                time.sleep(gap)
        self._last_call = time.monotonic()

    @staticmethod
    def _wait_for(headers, attempt: int) -> float:
        """Seconds the server asks us to wait: Retry-After (seconds or HTTP date), else
        X-RateLimit-Reset (epoch ms, OpenRouter's form, or s), else 2, 4, 8 ... capped at 60."""
        headers = headers or {}
        after = headers.get("Retry-After")
        if after:
            try:
                return max(0.0, float(after))
            except ValueError:
                try:
                    return max(0.0, parsedate_to_datetime(after).timestamp() - time.time())
                except (TypeError, ValueError):
                    pass
        reset = headers.get("X-RateLimit-Reset")
        if reset:
            try:
                at = float(reset)
                return max(0.0, (at / 1000 if at > 1e11 else at) - time.time())
            except ValueError:
                pass
        return min(60, 2 ** (attempt + 1))

    def generate(self, prompt: str, max_tokens: int = 600, temperature: float = 0.1,
                 json_mode: bool = False) -> Completion:
        messages = ([{"role": "system", "content": self.system}] if self.system else [])
        messages.append({"role": "user", "content": prompt})
        payload: Dict[str, Any] = {"model": self.model, "messages": messages,
                                   "temperature": temperature, "stream": False}
        if not self.uncapped:
            payload["max_tokens"] = max_tokens
        if json_mode:
            # Ollama, vLLM and llama.cpp all honour this; a server that does not simply
            # ignores it and the caller's own JSON extraction still runs.
            payload["response_format"] = {"type": "json_object"}
        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"})
        for attempt in range(self.retries + 1):
            self._throttle()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                if e.code != 429 or attempt == self.retries:
                    raise RuntimeError(f"local model at {self.base_url} unreachable: {e}") from e
                wait = self._wait_for(e.headers, attempt)
                h = e.headers or {}
                limit = "limit %s, remaining %s" % (h.get("X-RateLimit-Limit"),
                                                    h.get("X-RateLimit-Remaining"))
                if wait > self.max_wait:
                    raise RuntimeError(f"{self.model} rate limit resets in {wait:.0f}s, over "
                                       f"max_wait {self.max_wait:.0f}s ({limit})") from e
                print(f"429 from {self.model}: waiting {wait:.0f}s ({limit})",
                      file=sys.stderr, flush=True)
                time.sleep(wait)
            except urllib.error.URLError as e:
                raise RuntimeError(f"local model at {self.base_url} unreachable: {e}") from e
        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"unexpected response shape from {self.base_url}: {e}") from e
        usage = body.get("usage") or {}
        return Completion(text=text or "", model=self.model, raw=body,
                          prompt_tokens=usage.get("prompt_tokens"),
                          completion_tokens=usage.get("completion_tokens"))


    def unload(self) -> bool:
        """Ask the server to evict the model from memory.

        Ollama keeps a model resident for five minutes after the last call. On a 16GB
        machine a 5GB model still loaded is the difference between Maven starting and
        failing with 0xC0000142 (process initialisation failed) — which reads like a compile
        error and is not one. Call this before handing the machine to a build.
        """
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps({"model": self.model, "keep_alive": 0}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=30).read()
            return True
        except Exception:
            return False       # not an Ollama server, or already gone; not worth failing on


def free_all(base_url: str = DEFAULT_BASE_URL) -> dict:
    """Evict every model, then kill any inference server still holding memory.

    The API unload reported success for all seven models while two llama-server processes
    still held 7.5 GB between them — Ollama had spawned a second server the eviction never
    reached. That surplus is what starved the build JVMs and ended a multi-hour run with
    `fork: Resource temporarily unavailable`, so the API call alone is not enough.
    """
    import subprocess
    freed = [m for m in available_models(base_url)
             if LocalProvider(m, base_url).unload()]
    killed = []
    if os.name == "nt":
        for name in ("llama-server.exe", "ollama_llama_server.exe"):
            r = subprocess.run(["taskkill", "/F", "/IM", name],
                               capture_output=True, text=True)
            if r.returncode == 0:
                killed.append(name)
    return {"unloaded": freed, "servers_killed": killed}


def available_models(base_url: str = DEFAULT_BASE_URL, timeout: int = 10) -> list:
    """Model tags the local server is serving. Used to tell 'model not pulled' apart from
    'server down', which are the two failures worth distinguishing before a long run."""
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/v1/models", timeout=timeout) as r:
            return [m.get("id") for m in (json.loads(r.read().decode("utf-8")).get("data") or [])]
    except Exception:
        return []


def get_provider(spec: Dict[str, Any]):
    """Build a provider from the `model_provider` block in config (see config.py)."""
    kind = (spec or {}).get("type", "offline")
    if kind == "offline":
        return OfflineProvider()
    return LocalProvider(model=spec.get("model") or "nemotron",
                         base_url=spec.get("base_url") or DEFAULT_BASE_URL,
                         timeout=int(spec.get("timeout") or 300),
                         system=spec.get("system") or "")
