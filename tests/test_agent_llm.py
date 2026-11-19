"""LLM cascade: provider detection, fallback order and payload shapes.

The cascade is the only thing standing between an agent step and a dead run, so
the tests pin the order it tries providers in, that a failure moves to the next
one instead of ending the run, and exactly what each provider is sent.
"""

from __future__ import annotations

import pytest

from web3_agent_kit.agent.llm import LLM, LLMConfig

ENV_KEYS = [
    "ANTHROPIC_API_KEY",
    "KIMI_API_KEY",
    "OPENROUTER_API_KEY",
    "DEEPSEEK_API_KEY",
    "GROQ_API_KEY",
    "OPENAI_API_KEY",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _provider(name="openai", key="k", model="m", base="https://api.example/v1"):
    return {"name": name, "api_key": key, "model": model, "base_url": base}


class _Resp:
    def __init__(self, payload=None, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class TestDetection:
    def test_no_keys_gives_no_providers(self):
        assert LLMConfig().providers == []

    def test_constructing_without_any_key_raises(self):
        with pytest.raises(ValueError, match="No LLM providers"):
            LLM()

    def test_cascade_order_is_anthropic_then_openrouter_then_deepseek(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
        monkeypatch.setenv("OPENROUTER_API_KEY", "o")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "d")
        names = [p["base_url"] for p in LLMConfig().providers or []]
        assert "api.anthropic.com" in names[0]
        assert "openrouter.ai" in names[1]
        assert "deepseek.com" in names[2]

    def test_models_come_from_the_environment_when_set(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
        assert LLMConfig().providers[0]["model"] == "gpt-4o"

    def test_kimi_is_configured_as_openai_compatible(self, monkeypatch):
        monkeypatch.setenv("KIMI_API_KEY", "k")
        provider = LLMConfig().providers[0]
        assert provider["name"] == "openai"
        assert "moonshot" in provider["base_url"]

    def test_an_explicit_provider_list_is_kept(self):
        configured = [_provider()]
        assert LLMConfig(providers=configured).providers == configured

    def test_repr_lists_provider_kinds(self):
        assert repr(LLM(LLMConfig(providers=[_provider()]))) == "LLM(providers=['openai'])"


class TestCascade:
    def _llm(self, monkeypatch, behaviour):
        providers = [_provider(model="first"), _provider(model="second")]
        llm = LLM(LLMConfig(providers=providers))
        calls = []

        def fake(provider, messages, response_format):
            calls.append(provider["model"])
            outcome = behaviour[provider["model"]]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(llm, "_call_provider", fake)
        return llm, calls

    def test_the_first_success_wins(self, monkeypatch):
        llm, calls = self._llm(monkeypatch, {"first": "ok", "second": "later"})
        assert llm.chat("hi") == "ok"
        assert calls == ["first"]

    def test_a_failure_falls_through(self, monkeypatch):
        llm, calls = self._llm(monkeypatch, {"first": RuntimeError("429"), "second": "ok"})
        assert llm.chat("hi") == "ok"
        assert calls == ["first", "second"]

    def test_every_provider_failing_raises_with_the_last_error(self, monkeypatch):
        llm, _ = self._llm(
            monkeypatch, {"first": RuntimeError("429"), "second": RuntimeError("500")}
        )
        with pytest.raises(RuntimeError, match="All LLM providers failed.*500"):
            llm.chat("hi")


class TestMessages:
    def test_system_precedes_the_prompt(self, monkeypatch):
        llm = LLM(LLMConfig(providers=[_provider()]))
        captured = {}
        monkeypatch.setattr(
            llm, "_call_provider", lambda p, m, r: captured.setdefault("messages", m) and "ok"
        )
        llm.chat("hi", system="be terse")
        assert captured["messages"] == [
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "hi"},
        ]

    def test_an_explicit_message_list_overrides_prompt_and_system(self, monkeypatch):
        llm = LLM(LLMConfig(providers=[_provider()]))
        supplied = [{"role": "user", "content": "raw"}]
        captured = {}
        monkeypatch.setattr(
            llm, "_call_provider", lambda p, m, r: captured.setdefault("messages", m) and "ok"
        )
        llm.chat("ignored", system="ignored", messages=supplied)
        assert captured["messages"] is supplied

    def test_no_system_means_a_single_user_message(self, monkeypatch):
        llm = LLM(LLMConfig(providers=[_provider()]))
        captured = {}
        monkeypatch.setattr(
            llm, "_call_provider", lambda p, m, r: captured.setdefault("messages", m) and "ok"
        )
        llm.chat("hi")
        assert captured["messages"] == [{"role": "user", "content": "hi"}]


class TestPayload:
    def _llm(self, provider):
        return LLM(LLMConfig(providers=[provider]))

    def test_openai_json_mode_sets_response_format(self, monkeypatch):
        import requests

        sent = {}

        def post(url, headers=None, json=None, timeout=None):
            sent.update(url=url, headers=headers, json=json)
            return _Resp({"choices": [{"message": {"content": '{"a": 1}'}}]})

        monkeypatch.setattr(requests, "post", post)
        assert self._llm(_provider()).chat("x", response_format="json") == '{"a": 1}'
        assert sent["json"]["response_format"] == {"type": "json_object"}
        assert sent["headers"]["Authorization"] == "Bearer k"
        assert sent["url"].endswith("/chat/completions")

    def test_openrouter_gets_attribution_headers(self, monkeypatch):
        import requests

        sent = {}

        def post(url, headers=None, json=None, timeout=None):
            sent.update(headers=headers)
            return _Resp({"choices": [{"message": {"content": "ok"}}]})

        monkeypatch.setattr(requests, "post", post)
        self._llm(_provider(base="https://openrouter.ai/api/v1")).chat("x")
        assert sent["headers"]["X-Title"] == "web3-agent-kit"

    def test_anthropic_splits_the_system_message_out(self, monkeypatch):
        import requests

        sent = {}

        def post(url, headers=None, json=None, timeout=None):
            sent.update(url=url, headers=headers, json=json)
            return _Resp({"content": [{"text": "ok"}]})

        monkeypatch.setattr(requests, "post", post)
        provider = _provider("anthropic", base="https://api.anthropic.com/v1")
        assert self._llm(provider).chat("x", system="sys") == "ok"
        assert sent["json"]["system"] == "sys"
        assert sent["json"]["messages"] == [{"role": "user", "content": "x"}]
        assert sent["headers"]["x-api-key"] == "k"
        assert sent["url"].endswith("/messages")

    @pytest.mark.parametrize(("status", "match"), [(429, "Rate limited"), (503, "Server error")])
    def test_retryable_statuses_raise(self, monkeypatch, status, match):
        import requests

        monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp({}, status=status))
        with pytest.raises(RuntimeError, match=match):
            self._llm(_provider()).chat("x")


class TestJsonParsing:
    def test_plain_json(self, monkeypatch):
        llm = LLM(LLMConfig(providers=[_provider()]))
        monkeypatch.setattr(llm, "chat", lambda *a, **k: '{"a": 1}')
        assert llm.chat_json("x") == {"a": 1}

    def test_json_is_recovered_from_surrounding_prose(self, monkeypatch):
        llm = LLM(LLMConfig(providers=[_provider()]))
        monkeypatch.setattr(llm, "chat", lambda *a, **k: 'Sure:\n{"a": 2}\nDone.')
        assert llm.chat_json("x") == {"a": 2}

    def test_an_unparseable_answer_raises(self, monkeypatch):
        llm = LLM(LLMConfig(providers=[_provider()]))
        monkeypatch.setattr(llm, "chat", lambda *a, **k: "no json here")
        with pytest.raises(ValueError, match="Could not parse JSON"):
            llm.chat_json("x")
