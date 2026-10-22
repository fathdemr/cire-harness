import pytest

from cire_harness.providers import get_provider
from cire_harness.providers.anthropic import AnthropicProvider
from cire_harness.providers.base import ProviderError
from cire_harness.providers.fallback import PromptToolProvider
from cire_harness.providers.openai_compat import OpenAICompatProvider


def test_anthropic_native_by_default():
    provider = get_provider("anthropic:claude-opus-5-5", api_key="k")
    assert isinstance(provider, AnthropicProvider)
    assert provider.model == "claude-opus-5-5"


def test_ollama_defaults_to_prompt_tools_and_local_url():
    provider = get_provider("ollama:qwen2.5")
    assert isinstance(provider, PromptToolProvider)
    assert isinstance(provider.inner, OpenAICompatProvider)
    assert provider.inner.base_url == "http://localhost:11434/v1"
    assert provider.inner.api_key == ""


def test_ollama_native_when_requested():
    provider = get_provider("ollama:llama3.1", tool_mode="native")
    assert isinstance(provider, OpenAICompatProvider)


def test_openai_prompt_mode_wraps():
    provider = get_provider("openai:gpt-4o-mini", api_key="k", tool_mode="prompt")
    assert isinstance(provider, PromptToolProvider)


@pytest.mark.parametrize("spec", ["anthropic", "weird:model"])
def test_bad_spec_raises(spec):
    with pytest.raises(ProviderError):
        get_provider(spec)
