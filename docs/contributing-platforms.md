# Contributing Custom Platform Executors

This guide walks you through creating a custom platform executor for the
web3-agent-kit airdrop automation framework.

## Quick Start (5 Steps)

1. **Create your executor file** in `src/airdrop/executor/your_platform.py`
2. **Extend `BasePlatformExecutor`** and define your class
3. **Implement required methods**: `visit()`, `get_tasks()`, `complete_task()`
4. **Register your platform** via `PlatformPluginRegistry`
5. **Write tests** and submit a PR

---

## BasePlatformExecutor API

All platform executors extend `BasePlatformExecutor`, which provides:

### Class Attributes (set on your subclass)

| Attribute | Type | Description |
|-----------|------|-------------|
| `platform_name` | `str` | Unique platform identifier (e.g. `"galxe"`) |
| `platform_url` | `str` | Base URL of the platform |
| `supported_task_types` | `list[str]` | Task types your executor handles |

### Required Methods

```python
def visit(self, url: str) -> bool:
    """Navigate to the platform URL. Return True on success."""

def get_tasks(self) -> list[PlatformTask]:
    """Discover and return available tasks."""

def complete_task(self, task: PlatformTask) -> bool:
    """Execute a single task. Return True on success."""
```

### Optional Methods (with defaults)

```python
def complete_all(self, url: str, tracker=None) -> ExecutorResult:
    """Complete all tasks at URL. Default: visit → get_tasks → complete each."""

def verify(self) -> bool:
    """Verify task completion. Default: returns True."""

def get_results(self) -> ExecutorResult:
    """Return current results."""

def login(self, credentials: dict) -> bool:
    """Authenticate with the platform. Default: returns True (no auth needed)."""

def close(self) -> None:
    """Clean up resources (sessions, browser, etc.)."""
```

### Built-in Helpers

```python
# HTTP requests with rate limiting + retry
self._get(url, **kwargs) -> requests.Response
self._post(url, **kwargs) -> requests.Response

# Extract ID from platform URLs
self._extract_id_from_url(url) -> str

# Rate limiting
self._rate_limit()  # Enforces self.config.rate_limit_delay between calls
```

### Configuration

```python
from web3_agent_kit.airdrop.executor.base_executor import ExecutorConfig

config = ExecutorConfig(
    rate_limit_delay=2.0,    # Seconds between requests
    max_retries=3,           # Retry count on failure
    retry_delay=5.0,         # Base delay between retries
    timeout=30,              # HTTP timeout in seconds
    proxy=None,              # HTTP proxy URL
    captcha_api_key=None,    # CAPTCHA provider API key
    captcha_provider="anticaptcha",  # or "2captcha"
    verbose=False,
)
```

---

## Example: Adding a Custom Platform

Create `src/airdrop/executor/my_platform.py`:

```python
"""MyPlatform quest automation — API-based quest completion.

Handles MyPlatform quests, completes social tasks and verifies completion.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from .base_executor import (
    BasePlatformExecutor,
    ExecutorConfig,
    ExecutorResult,
    PlatformTask,
    TaskDifficulty,
)

logger = logging.getLogger(__name__)


@dataclass
class MyPlatformTask(PlatformTask):
    """A MyPlatform-specific task entry."""
    campaign_id: str = ""
    requires_verification: bool = False


@dataclass
class MyPlatformResult(ExecutorResult):
    """Result of farming a MyPlatform campaign."""
    xp_earned: int = 0
    badges_earned: int = 0


class MyPlatformExecutor(BasePlatformExecutor):
    """MyPlatform quest automation.

    Example::

        executor = MyPlatformExecutor(config)
        result = executor.complete_all("https://myplatform.io/quest/abc123")
        print(f"Completed {result.completed_tasks}/{result.total_tasks}")
    """

    platform_name = "my_platform"
    platform_url = "https://myplatform.io"
    supported_task_types = [
        "twitter_follow", "twitter_retweet",
        "discord_join", "telegram_join",
        "quiz", "visit_url", "custom",
    ]

    API_BASE = "https://api.myplatform.io"

    def __init__(self, config: Optional[ExecutorConfig] = None):
        super().__init__(config)
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        self._campaign_id: Optional[str] = None

    def visit(self, url: str) -> bool:
        """Load a MyPlatform quest page."""
        self._current_url = url
        self._campaign_id = self._extract_id_from_url(url)

        try:
            response = self._get(f"{self.API_BASE}/quest/{self._campaign_id}")
            if response.status_code == 200:
                logger.info(f"MyPlatform: quest loaded: {self._campaign_id}")
                return True
        except Exception as e:
            logger.debug(f"MyPlatform: API load failed: {e}")

        return True  # Assume page loads

    def get_tasks(self) -> list[MyPlatformTask]:
        """Parse available tasks from the loaded quest."""
        if not self._campaign_id:
            logger.error("MyPlatform: no quest loaded. Call visit() first.")
            return []

        try:
            response = self._get(
                f"{self.API_BASE}/quest/{self._campaign_id}/tasks"
            )
            data = response.json()

            tasks = []
            for i, task_data in enumerate(data.get("tasks", [])):
                tasks.append(MyPlatformTask(
                    task_id=f"myplat_{self._campaign_id}_{task_data['id']}",
                    title=task_data.get("title", f"Task {i}"),
                    task_type=task_data.get("type", "custom"),
                    points=task_data.get("points", 0),
                    campaign_id=self._campaign_id,
                ))

            return tasks

        except Exception as e:
            logger.error(f"MyPlatform: failed to get tasks: {e}")
            return []

    def complete_task(self, task: MyPlatformTask) -> bool:
        """Complete a single task."""
        if task.is_completed:
            return True

        try:
            response = self._post(
                f"{self.API_BASE}/task/{task.task_id}/complete",
                json={"campaign_id": self._campaign_id},
            )
            result = response.json()

            if result.get("success"):
                task.is_completed = True
                logger.info(f"MyPlatform: completed '{task.title}'")
                return True

            return False

        except Exception as e:
            logger.error(f"MyPlatform: task '{task.title}' failed: {e}")
            return False
```

### Register Your Executor

**Option A: Decorator** (in your executor file):

```python
from .plugin_registry import PlatformPluginRegistry

@PlatformPluginRegistry.from_class
class MyPlatformExecutor(BasePlatformExecutor):
    platform_name = "my_platform"
    ...
```

**Option B: Manual registration** (in `__init__.py` or elsewhere):

```python
from .my_platform import MyPlatformExecutor
from .plugin_registry import PlatformPluginRegistry

PlatformPluginRegistry.register("my_platform", MyPlatformExecutor)
```

**Option C: User plugin** (no code changes needed):

Drop `my_platform.py` into `~/.web3-agent-kit/plugins/` and it will be
auto-discovered on next startup.

---

## Task Types

Tasks use a standard type system for cross-platform compatibility:

### Social Tasks
- `twitter_follow` — Follow a Twitter/X account
- `twitter_retweet` — Retweet a tweet
- `twitter_like` — Like a tweet
- `twitter_comment` — Reply/comment on a tweet
- `discord_join` — Join a Discord server
- `discord_verify` — Verify in a Discord server
- `telegram_join` — Join a Telegram group/channel
- `youtube_subscribe` — Subscribe to a YouTube channel
- `github_star` — Star a GitHub repo
- `github_fork` — Fork a GitHub repo

### On-Chain Tasks
- `on_chain_tx` — Submit a transaction
- `on_chain_swap` — Execute a token swap
- `on_chain_bridge` — Bridge tokens across chains
- `on_chain_stake` — Stake tokens

### Other Tasks
- `quiz` — Answer quiz questions
- `visit_url` — Visit a URL
- `wallet_connect` — Connect a wallet
- `referral` — Use a referral link
- `custom` — Platform-specific task

### Difficulty Levels

```python
from web3_agent_kit.airdrop.executor.base_executor import TaskDifficulty

TaskDifficulty.EASY    # Social tasks, visits
TaskDifficulty.MEDIUM  # On-chain transactions, wallet connections
TaskDifficulty.HARD    # Cross-chain bridges, NFT mints
```

### Converting to AirdropTask

```python
task = PlatformTask(task_id="1", title="Follow", task_type="twitter_follow")
airdrop_task = task.to_airdrop_task("my_platform")
# → AirdropTask with task_id="my_platform_1", type=TaskType.SOCIAL_TWITTER_FOLLOW
```

---

## Anti-bot Handling

### Using the CAPTCHA Solver

```python
from web3_agent_kit.airdrop.executor.captcha_solver import (
    CaptchaSolver,
    CaptchaConfig,
    CaptchaProvider,
)

# Initialize
solver = CaptchaSolver(CaptchaConfig(
    provider=CaptchaProvider.ANTICAPTCHA,  # or TWOCAPTCHA
    api_key="your-api-key",
))

# Solve reCAPTCHA v2
token = solver.solve_recaptcha_v2(
    site_key="6Le-wvkSAAAAAPBMRTvw0Q4Muexq9bi0DJwx_mJ-",
    url="https://example.com",
)

# Solve GeeTest (used by Galxe)
solution = solver.solve_geetest(
    gt="abc123",
    challenge="def456",
    api_server="api.geetest.com",
)

# Solve hCaptcha
token = solver.solve_hcaptcha(site_key="xxx", url="https://example.com")

# Solve Cloudflare Turnstile
token = solver.solve_turnstile(site_key="xxx", url="https://example.com")

# Check balance
balance = solver.get_balance()  # Returns USD balance
```

### Integrating CAPTCHA in Your Executor

```python
def complete_task(self, task: MyPlatformTask) -> bool:
    if task.requires_captcha:
        from .captcha_solver import CaptchaSolver, CaptchaConfig, CaptchaProvider

        solver = CaptchaSolver(CaptchaConfig(
            provider=CaptchaProvider(self.config.captcha_provider),
            api_key=self.config.captcha_api_key,
        ))
        token = solver.solve_recaptcha_v2(
            site_key=task.metadata["recaptcha_site_key"],
            url=self._current_url,
        )
        # Include token in your API request
        payload = {"captcha_token": token}
    ...
```

### Supported CAPTCHA Providers

| Provider | Env Variable | Types |
|----------|-------------|-------|
| Anticaptcha | `ANTICAPTCHA_API_KEY` | reCAPTCHA v2/v3, hCaptcha, GeeTest, Turnstile |
| 2Captcha | `TWOCAPTCHA_API_KEY` | reCAPTCHA v2/v3, hCaptcha, GeeTest, Turnstile |

---

## Plugin System

### Auto-Discovery

On startup, the framework discovers executors from two locations:

1. **Built-in**: `src/airdrop/executor/*.py` (registered in `plugin_registry.py`)
2. **User plugins**: `~/.web3-agent-kit/plugins/*.py`

### Creating a User Plugin

1. Create `~/.web3-agent-kit/plugins/my_custom_executor.py`
2. Define a class that extends `BasePlatformExecutor`
3. Set `platform_name` on your class
4. It will be auto-discovered on next startup

```python
# ~/.web3-agent-kit/plugins/my_custom_executor.py
from web3_agent_kit.airdrop.executor.base_executor import BasePlatformExecutor, ExecutorConfig
from typing import Optional

class MyCustomExecutor(BasePlatformExecutor):
    platform_name = "my_custom"

    def __init__(self, config: Optional[ExecutorConfig] = None):
        super().__init__(config)

    def visit(self, url: str) -> bool:
        return True

    def get_tasks(self):
        return []

    def complete_task(self, task) -> bool:
        return True
```

### Using the Registry Programmatically

```python
from web3_agent_kit.airdrop.executor.plugin_registry import PlatformPluginRegistry

# List all available platforms
platforms = PlatformPluginRegistry.list_all()
print(list(platforms.keys()))

# Create an executor by name
executor = PlatformPluginRegistry.create_executor("galxe", config=my_config)

# Check if a platform exists
if PlatformPluginRegistry.has("my_custom"):
    executor = PlatformPluginRegistry.create_executor("my_custom")
```

---

## Testing

### Writing Tests

Create `tests/test_my_platform.py`:

```python
import pytest
from unittest.mock import MagicMock, patch
from web3_agent_kit.airdrop.executor.my_platform import MyPlatformExecutor, MyPlatformTask

class TestMyPlatformExecutor:
    def test_init(self):
        executor = MyPlatformExecutor()
        assert executor.platform_name == "my_platform"

    def test_has_methods(self):
        executor = MyPlatformExecutor()
        assert hasattr(executor, "visit")
        assert hasattr(executor, "get_tasks")
        assert hasattr(executor, "complete_task")
        assert hasattr(executor, "complete_all")

    @patch.object(MyPlatformExecutor, "_get")
    def test_visit(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"title": "Test"},
            raise_for_status=lambda: None,
        )
        executor = MyPlatformExecutor()
        assert executor.visit("https://myplatform.io/quest/abc123") is True

    @patch.object(MyPlatformExecutor, "_get")
    def test_get_tasks(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"tasks": [
                {"id": "1", "title": "Follow", "type": "twitter_follow", "points": 10}
            ]},
            raise_for_status=lambda: None,
        )
        executor = MyPlatformExecutor()
        executor._campaign_id = "test123"
        tasks = executor.get_tasks()
        assert len(tasks) == 1
        assert isinstance(tasks[0], MyPlatformTask)

    @patch.object(MyPlatformExecutor, "_post")
    def test_complete_task(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"success": True},
            raise_for_status=lambda: None,
        )
        executor = MyPlatformExecutor()
        task = MyPlatformTask(task_id="t1", title="Test", campaign_id="c1")
        assert executor.complete_task(task) is True
```

### Running Tests

```bash
# Run your tests
python -m pytest tests/test_my_platform.py -v --override-ini="addopts="

# Run all platform tests
python -m pytest tests/test_platforms.py -v --override-ini="addopts="

# Run with coverage
python -m pytest tests/test_my_platform.py -v --cov=web3_agent_kit.airdrop.executor.my_platform
```

### Mocking Best Practices

- Mock `self._get()` and `self._post()` to avoid real HTTP calls
- Use `MagicMock` for response objects with `.json()` and `.status_code`
- Test error paths (network failures, API errors, missing data)
- Test that `is_completed` is set correctly after task completion
- Test `close()` cleans up resources

---

## Checklist Before Submitting

- [ ] Executor extends `BasePlatformExecutor`
- [ ] `platform_name` is set and unique
- [ ] `visit()`, `get_tasks()`, `complete_task()` implemented
- [ ] Task dataclass extends `PlatformTask` (optional but recommended)
- [ ] Result dataclass extends `ExecutorResult` (optional but recommended)
- [ ] CAPTCHA integration if platform has anti-bot protection
- [ ] Tests cover init, visit, get_tasks, complete_task, close
- [ ] All tests pass: `python -m pytest tests/test_my_platform.py -v`
- [ ] Registered in `PlatformPluginRegistry` or placed in user plugins dir
