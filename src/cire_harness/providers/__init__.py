import os
from typing import Literal

from cire_harness.providers.anthropic import AnthropicProvider
from cire_harness.providers.base import Provider, ProviderError
from cire_harness.providers.fallback import PromptToolProvider
from cire_harness.providers.openai_compat import OpenAICompatProvider

ToolMode = Literal["native", "prompt", "auto"]

OLLAMA_URL = "http://localhost:11434/v1"


def get_provider(
    spec: str,
    base_url: str | None = None,
    api_key: str | None = None,
    tool_mode: ToolMode = "auto",
) -> Provider:
    kind, _, model = spec.partition(":")
    if not model:
        raise ProviderError(f"provider spec must look like kind:model, got {spec!r}")
    provider: Provider
    if kind == "anthropic":
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        provider = AnthropicProvider(
            model, api_key=key, base_url=base_url or "https://api.anthropic.com"
        )
        use_prompt = tool_mode == "prompt"
    elif kind == "openai":
        key = api_key or os.environ.get("OPENAI_API_KEY", "")
        provider = OpenAICompatProvider(
            model, base_url=base_url or "https://api.openai.com/v1", api_key=key
        )
        use_prompt = tool_mode == "prompt"
    elif kind == "ollama":
        provider = OpenAICompatProvider(model, base_url=base_url or OLLAMA_URL)
        provider.name = "ollama"
        use_prompt = tool_mode != "native"
    else:
        raise ProviderError(f"unknown provider kind {kind!r}")
    return PromptToolProvider(provider) if use_prompt else provider
