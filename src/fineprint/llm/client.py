"""A thin wrapper around any OpenAI-compatible chat endpoint.

Everything else in FinePrint depends on the small `LLM` protocol below, not on a vendor SDK, so the
provider can be swapped by changing three environment variables, and tests use a fake model.
"""
from __future__ import annotations

import json
import re
from typing import Any, Protocol

from ..config import Settings, get_settings


class LLM(Protocol):
    name: str

    def complete(self, system: str, user: str, *, json_mode: bool = False, max_tokens: int = 1500) -> str: ...


class LLMError(RuntimeError):
    pass


class OpenAICompatibleLLM:
    def __init__(self, settings: Settings):
        from openai import OpenAI

        kwargs: dict[str, Any] = {"api_key": settings.llm_api_key, "timeout": settings.llm_timeout_s, "max_retries": 1}
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        self._client = OpenAI(**kwargs)
        self._model = settings.llm_model
        self._temperature = settings.llm_temperature
        self.name = settings.llm_model

    def complete(self, system: str, user: str, *, json_mode: bool = False, max_tokens: int = 1500) -> str:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            if json_mode and "response_format" in str(exc):
                kwargs.pop("response_format", None)  # some providers do not support JSON mode
                response = self._client.chat.completions.create(**kwargs)
            else:
                raise LLMError(f"{type(exc).__name__}: {exc}") from exc
        return response.choices[0].message.content or ""


def get_llm(settings: Settings | None = None) -> LLM | None:
    settings = settings or get_settings()
    if not settings.llm_enabled:
        return None
    try:
        return OpenAICompatibleLLM(settings)
    except Exception:
        return None


def parse_json(text: str) -> Any:
    """Parse a model reply that should be JSON, tolerating code fences or a sentence around it."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        a, b = text.find(open_ch), text.rfind(close_ch)
        if a != -1 and b > a:
            try:
                return json.loads(text[a: b + 1])
            except json.JSONDecodeError:
                continue
    raise LLMError("The model did not return valid JSON.")
