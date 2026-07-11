# LLM
Multi-provider LLM client with cascade fallback.
The `LLM` class provides a unified interface for multiple LLM providers
with automatic fallback on failures.
---
## Classes

      members:
        - chat
        - chat_json
      show_root_heading: true
      show_source: true
---

      show_root_heading: true
      show_source: true
---
## Usage
### Auto-Detect Providers
```python
from web3_agent_kit.agent import LLM
# Automatically detects providers from environment variables
llm = LLM()
# Cascade order: Anthropic → Kimi → OpenRouter → DeepSeek → Groq → OpenAI
response = llm.chat("What is the best yield on Base?")
print(response)
```
### JSON Response
```python
data = llm.chat_json("Analyze this swap: 0.1 ETH to USDC on Base")
print(data)
# {
#   "analysis": "Good swap, low slippage expected",
#   "estimated_output": 350.0,
#   "gas_estimate": "0.002 ETH"
# }
```
### Custom Configuration
```python
from web3_agent_kit.agent import LLM, LLMConfig
config = LLMConfig(
    providers=[
        {
            "name": "anthropic",
            "api_key": "sk-ant-...",
            "model": "claude-sonnet-4-20250514",
            "base_url": "https://api.anthropic.com/v1",
        },
        {
            "name": "openai",
            "api_key": "sk-...",
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
        },
    ],
    temperature=0.1,
    max_tokens=2048,
    timeout=30,
)
llm = LLM(config=config)
```
---
## Supported Providers
| Provider | Env Variable | Default Model |
|----------|--------------|---------------|
| Anthropic | `ANTHROPIC_API_KEY` | `claude-sonnet-4-20250514` |
| OpenAI | `OPENAI_API_KEY` | `gpt-4o-mini` |
| Groq | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| OpenRouter | `OPENROUTER_API_KEY` | `anthropic/claude-sonnet-4` |
| Kimi | `KIMI_API_KEY` | `moonshot-v1-8k` |
---
## Error Handling
The LLM client automatically cascades through providers on failure:
- **429 (Rate Limited)** — Moves to next provider
- **5xx (Server Error)** — Moves to next provider
- **Timeout** — Moves to next provider
If all providers fail, raises `RuntimeError`.
