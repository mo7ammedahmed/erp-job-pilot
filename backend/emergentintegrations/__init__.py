"""Local stand-in for the Emergent platform's private `emergentintegrations` package.

The original package is only distributed through Emergent's private asset host, so the
backend cannot import it on a plain machine. This module re-implements the small surface
`ai.py` actually uses:

    LlmChat(...).with_model(provider, model)[.with_params(...)]
        .stream_message(UserMessage(text=...))     -> async iterator of TextDelta / StreamDone
        .send_message_multimodal_response(...)    -> (text, [image dicts])

Calls go to an OpenAI-compatible chat-completions endpoint. Configure it with
`EMERGENT_LLM_BASE_URL` plus a per-provider key, or leave it unset and every call raises
`LlmUnavailable` — `ai.py` surfaces that as a clean 502 instead of an ImportError at boot.

Note: this package intentionally shadows the real one when both are importable, so that a
local checkout always starts. Delete this directory if you install the genuine package.
"""

import os
import json

import httpx

__all__ = ["LlmChat", "UserMessage", "TextDelta", "StreamDone", "LlmUnavailable"]


class LlmUnavailable(RuntimeError):
    """Raised when no usable LLM endpoint/key is configured for the requested provider."""


class UserMessage:
    def __init__(self, text):
        self.text = text


class TextDelta:
    def __init__(self, content):
        self.content = content


class StreamDone:
    def __init__(self, finish_reason=None):
        self.finish_reason = finish_reason


# Provider -> (env var holding the key, default base url for that provider's OpenAI-compatible API)
_PROVIDERS = {
    "openai": ("OPENAI_API_KEY", "https://api.openai.com/v1"),
    "anthropic": ("ANTHROPIC_API_KEY", "https://api.anthropic.com/v1"),
    "gemini": ("GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai"),
    "nvidia": ("NVIDIA_API_KEY", "https://integrate.api.nvidia.com/v1"),
}


class LlmChat:
    def __init__(self, api_key=None, session_id=None, system_message=None, **kwargs):
        self.api_key = api_key
        self.session_id = session_id
        self.system_message = system_message
        self.provider = None
        self.model = None
        self.params = {}

    def with_model(self, provider, model):
        self.provider, self.model = provider, model
        return self

    def with_params(self, **params):
        self.params = {**self.params, **params}
        return self

    def _endpoint(self):
        """Resolve (base_url, key) or raise LlmUnavailable with an actionable message."""
        prov = (self.provider or "").lower()
        env_key, default_base = _PROVIDERS.get(prov, (f"{prov.upper()}_API_KEY", None))
        base = (os.environ.get("EMERGENT_LLM_BASE_URL") or "").strip().rstrip("/") or default_base
        key = (self.api_key or "").strip() or (os.environ.get(env_key) or "").strip()
        if not base:
            raise LlmUnavailable(f"No base URL configured for provider {prov!r}. Set EMERGENT_LLM_BASE_URL.")
        if not key:
            raise LlmUnavailable(
                f"No API key for provider {prov!r}. Set {env_key} (or EMERGENT_LLM_KEY) to enable AI features."
            )
        return base, key

    def _body(self):
        msgs = ([{"role": "system", "content": self.system_message}] if self.system_message else []) + \
               [{"role": "user", "content": m.text} for m in self._messages]
        return {
            "model": self.model,
            "messages": msgs,
            "temperature": self.params.get("temperature", 0.2),
            "max_tokens": self.params.get("max_tokens", 6000),
            "stream": True,
        }

    async def stream_message(self, message):
        self._messages = [message]
        base, key = self._endpoint()
        async with httpx.AsyncClient(timeout=180) as c:
            async with c.stream("POST", f"{base}/chat/completions",
                                headers={"Authorization": f"Bearer {key}"},
                                json=self._body()) as r:
                if r.status_code >= 400:
                    raise LlmUnavailable(f"{self.provider} returned HTTP {r.status_code}: {(await r.aread())[:300]!r}")
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    for ch in chunk.get("choices") or []:
                        piece = (ch.get("delta") or {}).get("content")
                        if piece:
                            yield TextDelta(piece)
                        if ch.get("finish_reason"):
                            yield StreamDone(ch["finish_reason"])
                            return

    async def send_message_multimodal_response(self, message):
        """Image generation is not implemented in the local shim."""
        raise LlmUnavailable(
            "Image generation needs the Emergent LLM gateway. Add a Gemini key, or call an image "
            "capable OpenAI-compatible endpoint via EMERGENT_LLM_BASE_URL."
        )
