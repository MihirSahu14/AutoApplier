"""Unified LLM client supporting multiple providers.

Anthropic uses the anthropic SDK.
Groq / Gemini / Ollama / OpenAI use the openai SDK with a custom base_url —
they all speak the OpenAI Chat Completions protocol.

Usage in scorer / tailor:
    from . import llm
    text = llm.chat(provider="groq", model="llama-3.1-8b-instant",
                    system=SYSTEM, user=user_block, max_tokens=800,
                    api_key=cfg["providers"]["groq"]["key"])
"""
import os
from typing import Optional

# Provider metadata.  `base_url=None` means use the provider SDK default.
PROVIDER_META: dict[str, dict] = {
    "anthropic": {
        "base_url": None,
        "env_key":  "ANTHROPIC_API_KEY",
        "free": False,
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "env_key":  "GROQ_API_KEY",
        "free": True,    # free tier: 14,400 req/day
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "env_key":  "GEMINI_API_KEY",
        "free": True,    # free tier: 1M tokens/day
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "env_key":  None,
        "free": True,    # fully local
    },
    "openai": {
        "base_url": None,
        "env_key":  "OPENAI_API_KEY",
        "free": False,
    },
}

# Token usage returned by chat() — used by budget tracking when provider is Anthropic.
class Usage:
    def __init__(self, input_tokens: int, output_tokens: int):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


def is_free(provider: str) -> bool:
    return PROVIDER_META.get(provider, {}).get("free", False)


def _resolve_key(provider: str, api_key: Optional[str]) -> str:
    if api_key:
        return api_key
    env = PROVIDER_META.get(provider, {}).get("env_key")
    return (os.environ.get(env, "") if env else "") or "ollama"


def chat(provider: str, model: str, system: str, user: str,
         max_tokens: int = 1000, api_key: Optional[str] = None) -> tuple[str, Usage]:
    """Call any supported provider. Returns (response_text, Usage)."""
    key = _resolve_key(provider, api_key)

    if provider == "anthropic":
        from anthropic import Anthropic
        client = Anthropic(api_key=key)
        msg = client.messages.create(
            model=model, max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text.strip(), Usage(
            msg.usage.input_tokens, msg.usage.output_tokens
        )

    # All others: OpenAI-compatible
    from openai import OpenAI
    base_url = PROVIDER_META.get(provider, {}).get("base_url")
    client = OpenAI(api_key=key, base_url=base_url)
    resp = client.chat.completions.create(
        model=model, max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    usage = resp.usage
    return resp.choices[0].message.content.strip(), Usage(
        usage.prompt_tokens if usage else 0,
        usage.completion_tokens if usage else 0,
    )
