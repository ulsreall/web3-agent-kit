"""Tests for LLM integration."""

import json
import pytest
from unittest.mock import MagicMock, patch

from web3_agent_kit.agent.llm import LLM, LLMConfig


class TestLLMConfig:
    """Test LLM configuration."""

    def test_auto_detect_no_env(self, monkeypatch):
        """Test auto-detect with no env vars."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("KIMI_API_KEY", raising=False)

        config = LLMConfig()
        assert config.providers == []

    def test_auto_detect_openai(self, monkeypatch):
        """Test auto-detect with OpenAI key."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123")
        config = LLMConfig()
        assert len(config.providers) == 1
        assert config.providers[0]["name"] == "openai"
        assert config.providers[0]["api_key"] == "sk-test123"

    def test_auto_detect_multiple(self, monkeypatch):
        """Test auto-detect with multiple keys."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
        config = LLMConfig()
        assert len(config.providers) == 2

    def test_custom_providers(self):
        """Test custom provider configuration."""
        providers = [
            {"name": "openai", "api_key": "test", "model": "gpt-4", "base_url": "https://api.openai.com/v1"},
        ]
        config = LLMConfig(providers=providers)
        assert len(config.providers) == 1
        assert config.providers[0]["model"] == "gpt-4"

    def test_default_params(self):
        """Test default parameters."""
        config = LLMConfig(providers=[{"name": "test"}])
        assert config.temperature == 0.1
        assert config.max_tokens == 2048
        assert config.timeout == 30


class TestLLM:
    """Test LLM client."""

    def test_no_providers_raises(self, monkeypatch):
        """Test that LLM raises with no providers."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("KIMI_API_KEY", raising=False)

        with pytest.raises(ValueError, match="No LLM providers configured"):
            LLM()

    def test_chat_openai(self):
        """Test chat with OpenAI provider."""
        providers = [
            {"name": "openai", "api_key": "test", "model": "gpt-4", "base_url": "https://api.openai.com/v1"},
        ]
        llm = LLM(config=LLMConfig(providers=providers))

        # Mock the _call_openai_compatible method
        llm._call_openai_compatible = MagicMock(return_value="Hello, world!")

        response = llm.chat("Hello")
        assert response == "Hello, world!"
        llm._call_openai_compatible.assert_called_once()

    def test_chat_json(self):
        """Test chat_json parsing."""
        providers = [
            {"name": "openai", "api_key": "test", "model": "gpt-4", "base_url": "https://api.openai.com/v1"},
        ]
        llm = LLM(config=LLMConfig(providers=providers))

        # Mock the chat method to return JSON string
        llm.chat = MagicMock(return_value='{"tool": "uniswap", "args": {"amount": 0.1}}')

        result = llm.chat_json("Swap 0.1 ETH")
        assert result["tool"] == "uniswap"
        assert result["args"]["amount"] == 0.1

    def test_cascade_fallback(self):
        """Test cascade fallback on failure."""
        providers = [
            {"name": "openai", "api_key": "test1", "model": "gpt-4", "base_url": "https://api.openai.com/v1"},
            {"name": "openai", "api_key": "test2", "model": "gpt-3.5-turbo", "base_url": "https://api.openai.com/v1"},
        ]
        llm = LLM(config=LLMConfig(providers=providers))

        # Mock _call_provider to fail on first, succeed on second
        call_count = [0]
        def mock_call_provider(provider, messages, response_format):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Rate limited")
            return "Success!"

        llm._call_provider = mock_call_provider

        response = llm.chat("Hello")
        assert response == "Success!"
        assert call_count[0] == 2

    def test_system_prompt(self):
        """Test chat with system prompt."""
        providers = [
            {"name": "openai", "api_key": "test", "model": "gpt-4", "base_url": "https://api.openai.com/v1"},
        ]
        llm = LLM(config=LLMConfig(providers=providers))

        # Capture the messages passed to _call_provider
        captured_messages = []
        def mock_call_provider(provider, messages, response_format):
            captured_messages.extend(messages)
            return "Response"

        llm._call_provider = mock_call_provider

        llm.chat("Hello", system="You are a helpful assistant")
        assert len(captured_messages) == 2
        assert captured_messages[0]["role"] == "system"
        assert captured_messages[0]["content"] == "You are a helpful assistant"
        assert captured_messages[1]["role"] == "user"
        assert captured_messages[1]["content"] == "Hello"

    def test_repr(self):
        """Test string representation."""
        providers = [
            {"name": "openai", "api_key": "test", "model": "gpt-4", "base_url": "https://api.openai.com/v1"},
            {"name": "anthropic", "api_key": "test", "model": "claude-3", "base_url": "https://api.anthropic.com/v1"},
        ]
        llm = LLM(config=LLMConfig(providers=providers))
        assert "openai" in repr(llm)
        assert "anthropic" in repr(llm)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
