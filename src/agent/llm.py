"""LLM integration — multi-provider cascade for agent reasoning.

Supports: OpenAI, Anthropic, Groq, DeepSeek, OpenRouter.
Falls back through providers on 429/5xx/timeout.

Usage:
    from web3_agent_kit.agent.llm import LLM

    llm = LLM()  # auto-detect from env vars
    response = llm.chat("What is the best yield on Base?")
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """Configuration for LLM providers."""

    providers: Optional[list[dict]] = None  # ordered list of providers to try
    temperature: float = 0.1
    max_tokens: int = 2048
    timeout: int = 30

    def __post_init__(self):
        if not self.providers:
            self.providers = self._auto_detect()

    def _auto_detect(self) -> list[dict]:
        """Auto-detect available providers from environment variables."""
        providers = []

        # Cascade order: Anthropic → Kimi → OpenRouter → DeepSeek → Groq
        if os.environ.get("ANTHROPIC_API_KEY"):
            providers.append({
                "name": "anthropic",
                "api_key": os.environ["ANTHROPIC_API_KEY"],
                "model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
                "base_url": "https://api.anthropic.com/v1",
            })

        if os.environ.get("KIMI_API_KEY"):
            providers.append({
                "name": "openai",
                "api_key": os.environ["KIMI_API_KEY"],
                "model": os.environ.get("KIMI_MODEL", "moonshot-v1-8k"),
                "base_url": os.environ.get("KIMI_BASE_URL", "https://api.moonshot.cn/v1"),
            })

        if os.environ.get("OPENROUTER_API_KEY"):
            providers.append({
                "name": "openai",
                "api_key": os.environ["OPENROUTER_API_KEY"],
                "model": os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4"),
                "base_url": "https://openrouter.ai/api/v1",
            })

        if os.environ.get("DEEPSEEK_API_KEY"):
            providers.append({
                "name": "openai",
                "api_key": os.environ["DEEPSEEK_API_KEY"],
                "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
                "base_url": "https://api.deepseek.com/v1",
            })

        if os.environ.get("GROQ_API_KEY"):
            providers.append({
                "name": "openai",
                "api_key": os.environ["GROQ_API_KEY"],
                "model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
                "base_url": "https://api.groq.com/openai/v1",
            })

        if os.environ.get("OPENAI_API_KEY"):
            providers.append({
                "name": "openai",
                "api_key": os.environ["OPENAI_API_KEY"],
                "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                "base_url": "https://api.openai.com/v1",
            })

        return providers


class LLM:
    """
    Multi-provider LLM client with cascade fallback.

    Tries providers in order. On 429/5xx/timeout, moves to next provider.

    Example:
        llm = LLM()
        response = llm.chat("Analyze this swap: 0.1 ETH to USDC")
    """

    def __init__(self, config: Optional[LLMConfig] = None, **kwargs):
        self.config = config or LLMConfig(**kwargs)
        if not self.config.providers:
            raise ValueError(
                "No LLM providers configured. Set one of: "
                "OPENAI_API_KEY, ANTHROPIC_API_KEY, GROQ_API_KEY, "
                "DEEPSEEK_API_KEY, OPENROUTER_API_KEY, KIMI_API_KEY"
            )

    def chat(
        self,
        prompt: str,
        system: Optional[str] = None,
        messages: Optional[list[dict]] = None,
        response_format: Optional[str] = None,
    ) -> str:
        """
        Send a chat completion request with cascade fallback.

        Args:
            prompt: User message
            system: System prompt
            messages: Full message list (overrides prompt/system if provided)
            response_format: "json" for JSON mode

        Returns:
            Assistant response text
        """
        if messages is None:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

        last_error = None
        for provider in self.config.providers:
            try:
                return self._call_provider(provider, messages, response_format)
            except Exception as e:
                last_error = e
                logger.warning(f"Provider {provider['name']} failed: {e}")
                continue

        raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")

    def chat_json(self, prompt: str, system: Optional[str] = None) -> dict:
        """
        Chat with JSON response parsing.

        Returns parsed JSON dict.
        """
        response = self.chat(prompt, system=system, response_format="json")
        # Try to extract JSON from response
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Try to find JSON in response
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
            raise ValueError(f"Could not parse JSON from response: {response[:200]}")

    def _call_provider(
        self, provider: dict, messages: list[dict], response_format: Optional[str]
    ) -> str:
        """Call a specific LLM provider."""
        import requests

        headers = {
            "Content-Type": "application/json",
        }

        payload = {
            "model": provider["model"],
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        if response_format == "json":
            if provider["name"] == "openai":
                payload["response_format"] = {"type": "json_object"}
            elif provider["name"] == "anthropic":
                # Anthropic doesn't have native JSON mode, use system prompt
                pass

        if provider["name"] == "anthropic":
            return self._call_anthropic(provider, messages, payload)
        else:
            return self._call_openai_compatible(provider, headers, payload)

    def _call_openai_compatible(
        self, provider: dict, headers: dict, payload: dict
    ) -> str:
        """Call OpenAI-compatible API."""
        import requests

        headers["Authorization"] = f"Bearer {provider['api_key']}"

        # Add provider-specific headers
        if provider.get("base_url", "").startswith("https://openrouter.ai"):
            headers["HTTP-Referer"] = "https://github.com/ulsreall/web3-agent-kit"
            headers["X-Title"] = "web3-agent-kit"

        url = f"{provider['base_url']}/chat/completions"

        resp = requests.post(
            url, headers=headers, json=payload, timeout=self.config.timeout
        )

        if resp.status_code == 429:
            raise RuntimeError(f"Rate limited by {provider['name']}")
        if resp.status_code >= 500:
            raise RuntimeError(f"Server error from {provider['name']}: {resp.status_code}")

        resp.raise_for_status()
        data = resp.json()

        return data["choices"][0]["message"]["content"]

    def _call_anthropic(
        self, provider: dict, messages: list[dict], payload: dict
    ) -> str:
        """Call Anthropic API."""
        import requests

        headers = {
            "Content-Type": "application/json",
            "x-api-key": provider["api_key"],
            "anthropic-version": "2023-06-01",
        }

        # Convert messages format
        system_msg = None
        api_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                api_messages.append(msg)

        payload = {
            "model": provider["model"],
            "max_tokens": self.config.max_tokens,
            "messages": api_messages,
        }
        if system_msg:
            payload["system"] = system_msg

        url = f"{provider['base_url']}/messages"

        resp = requests.post(
            url, headers=headers, json=payload, timeout=self.config.timeout
        )

        if resp.status_code == 429:
            raise RuntimeError(f"Rate limited by Anthropic")
        if resp.status_code >= 500:
            raise RuntimeError(f"Server error from Anthropic: {resp.status_code}")

        resp.raise_for_status()
        data = resp.json()

        return data["content"][0]["text"]

    def __repr__(self) -> str:
        names = [p["name"] for p in self.config.providers]
        return f"LLM(providers={names})"
