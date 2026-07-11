"""Tests for platform executors — airdrop task completion via API + browser.

Covers all new platform executors: QuestN, TaskOn, Intract, Port3, Galxe, Layer3.
Also covers CaptchaSolver, PlatformPluginRegistry, and BasePlatformExecutor.
"""

import json
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import fields

from web3_agent_kit.airdrop.executor.base_executor import (
    BasePlatformExecutor,
    ExecutorConfig,
    ExecutorResult,
    PlatformTask,
    TaskDifficulty,
)
from web3_agent_kit.airdrop.executor.questn import QuestNExecutor, QuestNTask, QuestNResult
from web3_agent_kit.airdrop.executor.taskon import TaskOnExecutor, TaskOnTask, TaskOnResult
from web3_agent_kit.airdrop.executor.intract_exec import IntractExecutor, IntractTask, IntractResult
from web3_agent_kit.airdrop.executor.port3_exec import Port3Executor, Port3Task, Port3Result
from web3_agent_kit.airdrop.executor.galxe_exec import GalxeExecutor, GalxeTask, GalxeResult
from web3_agent_kit.airdrop.executor.layer3_exec import Layer3Executor, Layer3Task, Layer3Result
from web3_agent_kit.airdrop.executor.captcha_solver import (
    CaptchaSolver,
    CaptchaConfig,
    CaptchaProvider,
    CaptchaSolvingError,
)
from web3_agent_kit.airdrop.executor.plugin_registry import PlatformPluginRegistry


# ─── Helpers ──────────────────────────────────────────────────

def _mock_response(json_data=None, status_code=200):
    """Create a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status.return_value = None
    return resp


def _make_concrete_subclass():
    """Create a minimal concrete subclass of BasePlatformExecutor for testing."""

    class DummyExecutor(BasePlatformExecutor):
        platform_name = "dummy"
        platform_url = "https://dummy.example.com"

        def visit(self, url):
            return True

        def get_tasks(self):
            return []

        def complete_task(self, task):
            return True

    return DummyExecutor


# ─── ExecutorConfig Tests ─────────────────────────────────────

class TestExecutorConfig:
    def test_defaults(self):
        cfg = ExecutorConfig()
        assert cfg.rate_limit_delay == 2.0
        assert cfg.max_retries == 3
        assert cfg.retry_delay == 5.0
        assert cfg.timeout == 30
        assert cfg.proxy is None
        assert cfg.captcha_api_key is None
        assert cfg.captcha_provider == "anticaptcha"
        assert cfg.verbose is False

    def test_custom_values(self):
        cfg = ExecutorConfig(
            rate_limit_delay=1.0,
            max_retries=5,
            retry_delay=10.0,
            timeout=60,
            proxy="http://proxy:8080",
            captcha_api_key="test-key",
            captcha_provider="2captcha",
            verbose=True,
        )
        assert cfg.rate_limit_delay == 1.0
        assert cfg.max_retries == 5
        assert cfg.retry_delay == 10.0
        assert cfg.timeout == 60
        assert cfg.proxy == "http://proxy:8080"
        assert cfg.captcha_api_key == "test-key"
        assert cfg.captcha_provider == "2captcha"
        assert cfg.verbose is True

    def test_user_agent_default(self):
        cfg = ExecutorConfig()
        assert "Mozilla" in cfg.user_agent
        assert "Chrome" in cfg.user_agent


# ─── PlatformTask Tests ──────────────────────────────────────

class TestPlatformTask:
    def test_creation(self):
        task = PlatformTask(task_id="1", title="Test Task")
        assert task.task_id == "1"
        assert task.title == "Test Task"
        assert task.description == ""
        assert task.task_type == "custom"
        assert task.points == 0
        assert task.is_completed is False
        assert task.is_claimable is False
        assert task.difficulty == TaskDifficulty.EASY
        assert task.metadata == {}

    def test_to_airdrop_task(self):
        task = PlatformTask(
            task_id="t1",
            title="Follow Twitter",
            task_type="twitter_follow",
            url="https://twitter.com/test",
            points=10,
        )
        airdrop = task.to_airdrop_task("test_platform")
        assert airdrop.task_id == "test_platform_t1"
        assert airdrop.platform == "test_platform"
        assert airdrop.title == "Follow Twitter"
        assert airdrop.points == 10

    def test_to_airdrop_task_completed(self):
        task = PlatformTask(task_id="t1", title="Done", is_completed=True)
        airdrop = task.to_airdrop_task("platform")
        from web3_agent_kit.airdrop.base import TaskStatus
        assert airdrop.status == TaskStatus.COMPLETED


# ─── ExecutorResult Tests ─────────────────────────────────────

class TestExecutorResult:
    def test_creation(self):
        result = ExecutorResult(platform="test", url="https://example.com")
        assert result.platform == "test"
        assert result.url == "https://example.com"
        assert result.total_tasks == 0
        assert result.completed_tasks == 0
        assert result.failed_tasks == 0

    def test_success_rate(self):
        result = ExecutorResult(platform="test", url="", total_tasks=10, completed_tasks=7)
        assert result.success_rate == 0.7

    def test_success_rate_zero_tasks(self):
        result = ExecutorResult(platform="test", url="", total_tasks=0)
        assert result.success_rate == 0.0

    def test_is_fully_completed(self):
        result = ExecutorResult(platform="test", url="", total_tasks=5, completed_tasks=5)
        assert result.is_fully_completed is True

    def test_not_fully_completed(self):
        result = ExecutorResult(platform="test", url="", total_tasks=5, completed_tasks=3)
        assert result.is_fully_completed is False

    def test_not_fully_completed_zero_tasks(self):
        result = ExecutorResult(platform="test", url="", total_tasks=0, completed_tasks=0)
        assert result.is_fully_completed is False


# ─── TaskDifficulty Tests ────────────────────────────────────

class TestTaskDifficulty:
    def test_values(self):
        assert TaskDifficulty.EASY.value == "easy"
        assert TaskDifficulty.MEDIUM.value == "medium"
        assert TaskDifficulty.HARD.value == "hard"


# ─── BasePlatformExecutor Tests ──────────────────────────────

class TestBasePlatformExecutor:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            BasePlatformExecutor()

    def test_subclass_instantiation(self):
        DummyExecutor = _make_concrete_subclass()
        executor = DummyExecutor()
        assert executor.platform_name == "dummy"
        assert executor.config is not None
        assert executor.session is not None

    def test_subclass_with_config(self):
        DummyExecutor = _make_concrete_subclass()
        cfg = ExecutorConfig(rate_limit_delay=0.5)
        executor = DummyExecutor(config=cfg)
        assert executor.config.rate_limit_delay == 0.5

    def test_subclass_with_proxy(self):
        DummyExecutor = _make_concrete_subclass()
        cfg = ExecutorConfig(proxy="http://proxy:3128")
        executor = DummyExecutor(config=cfg)
        assert executor.session.proxies["http"] == "http://proxy:3128"
        assert executor.session.proxies["https"] == "http://proxy:3128"

    def test_has_required_methods(self):
        DummyExecutor = _make_concrete_subclass()
        executor = DummyExecutor()
        assert hasattr(executor, "visit")
        assert hasattr(executor, "get_tasks")
        assert hasattr(executor, "complete_task")
        assert hasattr(executor, "complete_all")
        assert hasattr(executor, "verify")
        assert hasattr(executor, "get_results")
        assert hasattr(executor, "login")
        assert hasattr(executor, "close")
        assert hasattr(executor, "set_progress_callback")

    def test_context_manager(self):
        DummyExecutor = _make_concrete_subclass()
        executor = DummyExecutor()
        with executor as e:
            assert e is executor

    def test_login_default(self):
        DummyExecutor = _make_concrete_subclass()
        executor = DummyExecutor()
        assert executor.login({}) is True

    def test_verify_default(self):
        DummyExecutor = _make_concrete_subclass()
        executor = DummyExecutor()
        assert executor.verify() is True

    def test_set_progress_callback(self):
        DummyExecutor = _make_concrete_subclass()
        executor = DummyExecutor()
        cb = MagicMock()
        executor.set_progress_callback(cb)
        assert executor._progress_callback is cb

    def test_get_results_default(self):
        DummyExecutor = _make_concrete_subclass()
        executor = DummyExecutor()
        result = executor.get_results()
        assert isinstance(result, ExecutorResult)

    def test_extract_id_from_url(self):
        DummyExecutor = _make_concrete_subclass()
        executor = DummyExecutor()
        url = "https://example.com/path/abc123def456789012345678"
        # _extract_id_from_url tries to find 24-char hex first
        assert executor._extract_id_from_url(url) == "abc123def456789012345678"

    def test_extract_id_fallback(self):
        DummyExecutor = _make_concrete_subclass()
        executor = DummyExecutor()
        url = "https://example.com/path/to/my-item"
        assert executor._extract_id_from_url(url) == "my-item"


# ─── QuestN Executor Tests ────────────────────────────────────

class TestQuestNExecutor:
    def test_init(self):
        executor = QuestNExecutor()
        assert executor.platform_name == "questn"
        assert executor.platform_url == "https://questn.xyz"
        assert executor._campaign_id is None

    def test_init_with_config(self):
        cfg = ExecutorConfig(rate_limit_delay=1.0)
        executor = QuestNExecutor(config=cfg)
        assert executor.config.rate_limit_delay == 1.0

    def test_has_methods(self):
        executor = QuestNExecutor()
        assert hasattr(executor, "visit")
        assert hasattr(executor, "get_tasks")
        assert hasattr(executor, "complete_task")
        assert hasattr(executor, "complete_all")
        assert hasattr(executor, "close")

    def test_supported_task_types(self):
        executor = QuestNExecutor()
        assert "twitter_follow" in executor.supported_task_types
        assert "discord_join" in executor.supported_task_types
        assert "quiz" in executor.supported_task_types

    def test_api_base(self):
        assert QuestNExecutor.API_BASE == "https://api.questn.xyz"

    @patch.object(QuestNExecutor, "_get")
    def test_visit_success(self, mock_get):
        mock_get.return_value = _mock_response({"title": "Test Quest"})
        executor = QuestNExecutor()
        result = executor.visit("https://questn.xyz/quest/abc123def456789012345678")
        assert result is True
        assert executor._campaign_id == "abc123def456789012345678"

    @patch.object(QuestNExecutor, "_get")
    def test_visit_api_failure(self, mock_get):
        mock_get.side_effect = Exception("Network error")
        executor = QuestNExecutor()
        result = executor.visit("https://questn.xyz/quest/abc123")
        assert result is True  # Falls back to True

    @patch.object(QuestNExecutor, "_get")
    def test_get_tasks(self, mock_get):
        mock_get.return_value = _mock_response({
            "tasks": [
                {"id": "1", "title": "Follow Twitter", "type": "twitter_follow", "points": 10},
                {"id": "2", "title": "Join Discord", "type": "discord_join", "points": 5},
            ]
        })
        executor = QuestNExecutor()
        executor._campaign_id = "test123"
        tasks = executor.get_tasks()
        assert len(tasks) == 2
        assert tasks[0].title == "Follow Twitter"
        assert isinstance(tasks[0], QuestNTask)

    def test_get_tasks_no_campaign(self):
        executor = QuestNExecutor()
        tasks = executor.get_tasks()
        assert tasks == []

    @patch.object(QuestNExecutor, "_post")
    def test_complete_task(self, mock_post):
        mock_post.return_value = _mock_response({"success": True})
        executor = QuestNExecutor()
        task = QuestNTask(task_id="q1", title="Test", quest_id="q1", quest_type="twitter_follow")
        result = executor.complete_task(task)
        assert result is True

    def test_complete_task_already_done(self):
        executor = QuestNExecutor()
        task = QuestNTask(task_id="q1", title="Test", is_completed=True)
        assert executor.complete_task(task) is True


# ─── TaskOn Executor Tests ────────────────────────────────────

class TestTaskOnExecutor:
    def test_init(self):
        executor = TaskOnExecutor()
        assert executor.platform_name == "taskon"
        assert executor.platform_url == "https://taskon.xyz"
        assert executor._campaign_id is None

    def test_init_with_config(self):
        cfg = ExecutorConfig(timeout=60)
        executor = TaskOnExecutor(config=cfg)
        assert executor.config.timeout == 60

    def test_has_methods(self):
        executor = TaskOnExecutor()
        assert hasattr(executor, "visit")
        assert hasattr(executor, "get_tasks")
        assert hasattr(executor, "complete_task")
        assert hasattr(executor, "complete_all")
        assert hasattr(executor, "close")

    def test_supported_task_types(self):
        executor = TaskOnExecutor()
        assert "twitter_follow" in executor.supported_task_types
        assert "wallet_connect" in executor.supported_task_types

    def test_api_base(self):
        assert TaskOnExecutor.API_BASE == "https://api.taskon.xyz"

    @patch.object(TaskOnExecutor, "_get")
    def test_visit_success(self, mock_get):
        mock_get.return_value = _mock_response({"name": "Test Campaign"})
        executor = TaskOnExecutor()
        result = executor.visit("https://taskon.xyz/campaign/abc123def456789012345678")
        assert result is True
        assert executor._campaign_id == "abc123def456789012345678"

    @patch.object(TaskOnExecutor, "_get")
    def test_get_tasks(self, mock_get):
        mock_get.return_value = _mock_response({
            "tasks": [
                {"id": "1", "title": "Follow", "type": "twitter_follow", "points": 10},
            ]
        })
        executor = TaskOnExecutor()
        executor._campaign_id = "test123"
        tasks = executor.get_tasks()
        assert len(tasks) == 1
        assert isinstance(tasks[0], TaskOnTask)

    @patch.object(TaskOnExecutor, "_post")
    def test_complete_task(self, mock_post):
        mock_post.return_value = _mock_response({"success": True})
        executor = TaskOnExecutor()
        executor._campaign_id = "camp1"
        task = TaskOnTask(task_id="t1", title="Test", campaign_id="camp1")
        assert executor.complete_task(task) is True

    def test_complete_task_already_done(self):
        executor = TaskOnExecutor()
        task = TaskOnTask(task_id="t1", title="Test", is_completed=True)
        assert executor.complete_task(task) is True


# ─── Intract Executor Tests ───────────────────────────────────

class TestIntractExecutor:
    def test_init(self):
        executor = IntractExecutor()
        assert executor.platform_name == "intract"
        assert executor.platform_url == "https://intract.io"
        assert executor._campaign_id is None
        assert executor._auth_token is None

    def test_init_with_config(self):
        cfg = ExecutorConfig(captcha_api_key="test-key")
        executor = IntractExecutor(config=cfg)
        assert executor.config.captcha_api_key == "test-key"

    def test_has_methods(self):
        executor = IntractExecutor()
        assert hasattr(executor, "visit")
        assert hasattr(executor, "get_tasks")
        assert hasattr(executor, "complete_task")
        assert hasattr(executor, "complete_all")
        assert hasattr(executor, "login")
        assert hasattr(executor, "close")

    def test_supported_task_types(self):
        executor = IntractExecutor()
        assert "content_creation" in executor.supported_task_types
        assert "twitter_follow" in executor.supported_task_types

    @patch.object(IntractExecutor, "_get")
    def test_visit_success(self, mock_get):
        mock_get.return_value = _mock_response({"id": "q1", "title": "Test Quest"})
        executor = IntractExecutor()
        result = executor.visit("https://intract.io/quest/abc123def456789012345678")
        assert result is True

    @patch.object(IntractExecutor, "_get")
    def test_get_tasks(self, mock_get):
        mock_get.return_value = _mock_response({
            "tasks": [
                {"id": "1", "title": "Like Tweet", "type": "twitter_like", "points": 5},
            ]
        })
        executor = IntractExecutor()
        executor._campaign_id = "camp1"
        tasks = executor.get_tasks()
        assert len(tasks) == 1
        assert isinstance(tasks[0], IntractTask)

    @patch.object(IntractExecutor, "_post")
    def test_complete_task(self, mock_post):
        mock_post.return_value = _mock_response({"success": True})
        executor = IntractExecutor()
        executor._campaign_id = "camp1"
        executor._quest_id = "q1"
        task = IntractTask(task_id="t1", title="Test", campaign_id="camp1", quest_id="q1")
        assert executor.complete_task(task) is True

    def test_login_with_token(self):
        executor = IntractExecutor()
        result = executor.login({"token": "my-token"})
        assert result is True
        assert executor._auth_token == "my-token"


# ─── Port3 Executor Tests ─────────────────────────────────────

class TestPort3Executor:
    def test_init(self):
        executor = Port3Executor()
        assert executor.platform_name == "port3"
        assert executor.platform_url == "https://port3.io"
        assert executor._campaign_id is None

    def test_init_with_config(self):
        cfg = ExecutorConfig(max_retries=5)
        executor = Port3Executor(config=cfg)
        assert executor.config.max_retries == 5

    def test_has_methods(self):
        executor = Port3Executor()
        assert hasattr(executor, "visit")
        assert hasattr(executor, "get_tasks")
        assert hasattr(executor, "complete_task")
        assert hasattr(executor, "complete_all")
        assert hasattr(executor, "login")
        assert hasattr(executor, "close")

    def test_supported_task_types(self):
        executor = Port3Executor()
        assert "social_aggregation" in executor.supported_task_types

    @patch.object(Port3Executor, "_get")
    def test_visit_success(self, mock_get):
        mock_get.return_value = _mock_response({"title": "Test Quest"})
        executor = Port3Executor()
        result = executor.visit("https://port3.io/quest/abc123def456789012345678")
        assert result is True

    @patch.object(Port3Executor, "_get")
    def test_get_tasks(self, mock_get):
        mock_get.return_value = _mock_response({
            "tasks": [
                {"id": "1", "title": "Social Task", "type": "twitter_follow", "points": 10},
            ]
        })
        executor = Port3Executor()
        executor._campaign_id = "camp1"
        tasks = executor.get_tasks()
        assert len(tasks) == 1
        assert isinstance(tasks[0], Port3Task)

    @patch.object(Port3Executor, "_post")
    def test_complete_task(self, mock_post):
        mock_post.return_value = _mock_response({"success": True})
        executor = Port3Executor()
        executor._campaign_id = "camp1"
        task = Port3Task(task_id="t1", title="Test", campaign_id="camp1")
        assert executor.complete_task(task) is True

    def test_login_with_token(self):
        executor = Port3Executor()
        result = executor.login({"token": "my-token"})
        assert result is True
        assert executor._auth_token == "my-token"

    def test_login_no_credentials(self):
        executor = Port3Executor()
        result = executor.login({})
        assert result is False


# ─── Galxe Executor Tests ─────────────────────────────────────

class TestGalxeExecutor:
    def test_init(self):
        executor = GalxeExecutor()
        assert executor.platform_name == "galxe"
        assert executor.platform_url == "https://app.galxe.com"
        assert executor._campaign_id is None
        assert executor._wallet_address is None

    def test_init_with_config(self):
        cfg = ExecutorConfig(captcha_provider="2captcha")
        executor = GalxeExecutor(config=cfg)
        assert executor.config.captcha_provider == "2captcha"

    def test_has_methods(self):
        executor = GalxeExecutor()
        assert hasattr(executor, "visit")
        assert hasattr(executor, "get_tasks")
        assert hasattr(executor, "complete_task")
        assert hasattr(executor, "complete_all")
        assert hasattr(executor, "login")
        assert hasattr(executor, "close")
        assert hasattr(executor, "get_campaigns")
        assert hasattr(executor, "verify_credentials")
        assert hasattr(executor, "claim_reward")

    def test_supported_task_types(self):
        executor = GalxeExecutor()
        assert "nft_mint" in executor.supported_task_types
        assert "on_chain_swap" in executor.supported_task_types
        assert "referral" in executor.supported_task_types

    def test_graphql_api(self):
        assert GalxeExecutor.GRAPHQL_API == "https://graphigo.prd.galaxy.eco/query"

    @patch.object(GalxeExecutor, "_post")
    def test_visit_success(self, mock_post):
        mock_post.return_value = _mock_response({
            "data": {
                "campaign": {
                    "id": "123",
                    "name": "Test Campaign",
                    "tasks": [],
                }
            }
        })
        executor = GalxeExecutor()
        result = executor.visit("https://app.galxe.com/quest/abc123def456789012345678")
        assert result is True
        assert executor._campaign_data is not None

    @patch.object(GalxeExecutor, "_post")
    def test_visit_failure(self, mock_post):
        mock_post.return_value = _mock_response({"data": {"campaign": None}})
        executor = GalxeExecutor()
        result = executor.visit("https://app.galxe.com/quest/abc123")
        assert result is False

    def test_get_tasks_no_campaign(self):
        executor = GalxeExecutor()
        tasks = executor.get_tasks()
        assert tasks == []

    @patch.object(GalxeExecutor, "_post")
    def test_complete_task(self, mock_post):
        mock_post.return_value = _mock_response({"success": True})
        executor = GalxeExecutor()
        executor._campaign_id = "camp1"
        task = GalxeTask(task_id="t1", title="Test", campaign_id="camp1", task_id_galxe="gt1")
        assert executor.complete_task(task) is True

    def test_login_with_wallet(self):
        executor = GalxeExecutor()
        result = executor.login({"wallet_address": "0x1234567890abcdef"})
        assert result is True
        assert executor._wallet_address == "0x1234567890abcdef"

    def test_login_no_wallet(self):
        executor = GalxeExecutor()
        result = executor.login({})
        assert result is False


# ─── Layer3 Executor Tests ────────────────────────────────────

class TestLayer3Executor:
    def test_init(self):
        executor = Layer3Executor()
        assert executor.platform_name == "layer3"
        assert executor.platform_url == "https://layer3.xyz"
        assert executor._quest_id is None
        assert executor._auth_token is None

    def test_init_with_config(self):
        cfg = ExecutorConfig(retry_delay=2.0)
        executor = Layer3Executor(config=cfg)
        assert executor.config.retry_delay == 2.0

    def test_has_methods(self):
        executor = Layer3Executor()
        assert hasattr(executor, "visit")
        assert hasattr(executor, "get_tasks")
        assert hasattr(executor, "complete_task")
        assert hasattr(executor, "complete_all")
        assert hasattr(executor, "login")
        assert hasattr(executor, "close")
        assert hasattr(executor, "get_quests")
        assert hasattr(executor, "verify_on_chain")

    def test_supported_task_types(self):
        executor = Layer3Executor()
        assert "cross_chain" in executor.supported_task_types
        assert "on_chain_bridge" in executor.supported_task_types
        assert "wallet_connect" in executor.supported_task_types

    @patch.object(Layer3Executor, "_get")
    def test_visit_success(self, mock_get):
        mock_get.return_value = _mock_response({"title": "Test Quest", "steps": []})
        executor = Layer3Executor()
        result = executor.visit("https://layer3.xyz/quests/abc123def456789012345678")
        assert result is True
        assert executor._quest_id == "abc123def456789012345678"

    def test_get_tasks_no_quest(self):
        executor = Layer3Executor()
        tasks = executor.get_tasks()
        assert tasks == []

    @patch.object(Layer3Executor, "_get")
    def test_get_quests(self, mock_get):
        mock_get.return_value = _mock_response({
            "quests": [{"id": "q1", "title": "Quest 1"}]
        })
        executor = Layer3Executor()
        quests = executor.get_quests()
        assert len(quests) == 1

    @patch.object(Layer3Executor, "_post")
    def test_complete_task(self, mock_post):
        mock_post.return_value = _mock_response({"success": True})
        executor = Layer3Executor()
        executor._quest_id = "q1"
        task = Layer3Task(task_id="t1", title="Test", quest_id="q1", step_id="s1")
        assert executor.complete_task(task) is True

    def test_login_with_token(self):
        executor = Layer3Executor()
        result = executor.login({"token": "my-token"})
        assert result is True
        assert executor._auth_token == "my-token"

    def test_login_no_credentials(self):
        executor = Layer3Executor()
        result = executor.login({})
        assert result is False


# ─── Platform-Specific Task Dataclass Tests ──────────────────

class TestQuestNTask:
    def test_creation(self):
        task = QuestNTask(task_id="1", title="Test", quest_id="q1", quest_type="twitter_follow")
        assert task.quest_id == "q1"
        assert task.quest_type == "twitter_follow"
        assert task.required is True
        assert task.verification_type == "auto"

    def test_inherits_platform_task(self):
        task = QuestNTask(task_id="1", title="Test")
        assert isinstance(task, PlatformTask)


class TestTaskOnTask:
    def test_creation(self):
        task = TaskOnTask(task_id="1", title="Test", campaign_id="c1")
        assert task.campaign_id == "c1"
        assert task.action_data == {}
        assert isinstance(task, PlatformTask)


class TestIntractTask:
    def test_creation(self):
        task = IntractTask(task_id="1", title="Test", campaign_id="c1", quest_id="q1")
        assert task.requires_captcha is False
        assert task.verification_type == "auto"
        assert isinstance(task, PlatformTask)


class TestPort3Task:
    def test_creation(self):
        task = Port3Task(task_id="1", title="Test", campaign_id="c1")
        assert task.aggregation_type == ""
        assert task.chain_id is None
        assert isinstance(task, PlatformTask)


class TestGalxeTask:
    def test_creation(self):
        task = GalxeTask(task_id="1", title="Test", campaign_id="c1")
        assert task.credential_id == ""
        assert task.task_id_galxe == ""
        assert task.chain_id is None
        assert task.contract_address == ""
        assert isinstance(task, PlatformTask)


class TestLayer3Task:
    def test_creation(self):
        task = Layer3Task(task_id="1", title="Test", quest_id="q1")
        assert task.step_id == ""
        assert task.chain_name == ""
        assert task.requires_wallet is False
        assert isinstance(task, PlatformTask)


# ─── Platform-Specific Result Dataclass Tests ────────────────

class TestQuestNResult:
    def test_creation(self):
        result = QuestNResult(platform="questn", url="")
        assert result.xp_earned == 0
        assert result.level_up is False
        assert isinstance(result, ExecutorResult)


class TestTaskOnResult:
    def test_creation(self):
        result = TaskOnResult(platform="taskon", url="")
        assert result.campaign_name == ""
        assert result.rewards_claimed == 0
        assert isinstance(result, ExecutorResult)


class TestIntractResult:
    def test_creation(self):
        result = IntractResult(platform="intract", url="")
        assert result.xp_earned == 0
        assert result.badges_earned == 0
        assert isinstance(result, ExecutorResult)


class TestPort3Result:
    def test_creation(self):
        result = Port3Result(platform="port3", url="")
        assert result.xp_earned == 0
        assert result.reputation_score == 0
        assert isinstance(result, ExecutorResult)


class TestGalxeResult:
    def test_creation(self):
        result = GalxeResult(platform="galxe", url="")
        assert result.credentials_verified == 0
        assert result.reward_claimed is False
        assert isinstance(result, ExecutorResult)


class TestLayer3Result:
    def test_creation(self):
        result = Layer3Result(platform="layer3", url="")
        assert result.xp_earned == 0
        assert result.tokens_earned == 0.0
        assert result.chains_interacted == []
        assert isinstance(result, ExecutorResult)


# ─── CaptchaSolver Tests ──────────────────────────────────────

class TestCaptchaConfig:
    def test_defaults(self):
        cfg = CaptchaConfig()
        assert cfg.provider == CaptchaProvider.ANTICAPTCHA
        assert cfg.api_key is None
        assert cfg.timeout == 120
        assert cfg.max_retries == 3
        assert cfg.retry_delay == 5.0
        assert cfg.poll_interval == 5.0

    def test_custom(self):
        cfg = CaptchaConfig(
            provider=CaptchaProvider.TWOCAPTCHA,
            api_key="test-key",
            timeout=60,
        )
        assert cfg.provider == CaptchaProvider.TWOCAPTCHA
        assert cfg.api_key == "test-key"
        assert cfg.timeout == 60


class TestCaptchaProvider:
    def test_values(self):
        assert CaptchaProvider.ANTICAPTCHA.value == "anticaptcha"
        assert CaptchaProvider.TWOCAPTCHA.value == "2captcha"


class TestCaptchaSolver:
    def test_init_default(self):
        solver = CaptchaSolver()
        assert solver.config is not None
        assert solver.session is not None

    def test_init_with_config(self):
        cfg = CaptchaConfig(api_key="test-key", provider=CaptchaProvider.TWOCAPTCHA)
        solver = CaptchaSolver(config=cfg)
        assert solver.config.api_key == "test-key"
        assert solver.config.provider == CaptchaProvider.TWOCAPTCHA

    @patch.dict("os.environ", {"ANTICAPTCHA_API_KEY": "env-key"})
    def test_init_from_env(self):
        solver = CaptchaSolver(CaptchaConfig(provider=CaptchaProvider.ANTICAPTCHA))
        assert solver.config.api_key == "env-key"

    @patch.dict("os.environ", {"TWOCAPTCHA_API_KEY": "env-key-2c"})
    def test_init_from_env_2captcha(self):
        solver = CaptchaSolver(CaptchaConfig(provider=CaptchaProvider.TWOCAPTCHA))
        assert solver.config.api_key == "env-key-2c"

    def test_has_methods(self):
        solver = CaptchaSolver()
        assert hasattr(solver, "solve_recaptcha_v2")
        assert hasattr(solver, "solve_recaptcha_v3")
        assert hasattr(solver, "solve_hcaptcha")
        assert hasattr(solver, "solve_geetest")
        assert hasattr(solver, "solve_turnstile")
        assert hasattr(solver, "get_balance")

    @patch("web3_agent_kit.airdrop.executor.captcha_solver.requests.Session")
    def test_get_balance_anticaptcha(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.post.return_value = _mock_response({"balance": 15.5, "errorId": 0})

        cfg = CaptchaConfig(provider=CaptchaProvider.ANTICAPTCHA, api_key="test-key")
        solver = CaptchaSolver(config=cfg)
        solver.session = mock_session
        balance = solver.get_balance()
        assert balance == 15.5

    @patch("web3_agent_kit.airdrop.executor.captcha_solver.requests.Session")
    def test_get_balance_2captcha(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.get.return_value = _mock_response({"status": 1, "request": "7.234"})

        cfg = CaptchaConfig(provider=CaptchaProvider.TWOCAPTCHA, api_key="test-key")
        solver = CaptchaSolver(config=cfg)
        solver.session = mock_session
        balance = solver.get_balance()
        assert balance == 7.234

    def test_get_balance_no_key_anticaptcha(self):
        cfg = CaptchaConfig(provider=CaptchaProvider.ANTICAPTCHA, api_key=None)
        solver = CaptchaSolver(config=cfg)
        # If no key from env either, should raise
        with patch.dict("os.environ", {"ANTICAPTCHA_API_KEY": ""}, clear=False):
            solver.config.api_key = None
            with pytest.raises(CaptchaSolvingError):
                solver.get_balance()


class TestCaptchaSolvingError:
    def test_is_exception(self):
        err = CaptchaSolvingError("test error")
        assert isinstance(err, Exception)
        assert str(err) == "test error"


# ─── PlatformPluginRegistry Tests ─────────────────────────────

class TestPlatformPluginRegistry:
    def setup_method(self):
        PlatformPluginRegistry.clear()

    def teardown_method(self):
        PlatformPluginRegistry.clear()

    def test_register_and_get(self):
        DummyExecutor = _make_concrete_subclass()
        PlatformPluginRegistry.register("dummy", DummyExecutor)
        assert PlatformPluginRegistry.get("dummy") is DummyExecutor

    def test_register_case_insensitive(self):
        DummyExecutor = _make_concrete_subclass()
        PlatformPluginRegistry.register("Dummy", DummyExecutor)
        assert PlatformPluginRegistry.get("dummy") is DummyExecutor
        assert PlatformPluginRegistry.get("DUMMY") is DummyExecutor

    def test_get_nonexistent(self):
        PlatformPluginRegistry._discovered = True  # skip auto-discover
        assert PlatformPluginRegistry.get("nonexistent") is None

    def test_register_type_check(self):
        with pytest.raises(TypeError):
            PlatformPluginRegistry.register("bad", "not a class")

    def test_register_non_subclass(self):
        with pytest.raises(TypeError):
            PlatformPluginRegistry.register("bad", dict)

    def test_list_all(self):
        DummyExecutor = _make_concrete_subclass()
        PlatformPluginRegistry.register("dummy1", DummyExecutor)
        PlatformPluginRegistry.register("dummy2", DummyExecutor)
        all_executors = PlatformPluginRegistry.list_all()
        assert "dummy1" in all_executors
        assert "dummy2" in all_executors

    def test_has(self):
        DummyExecutor = _make_concrete_subclass()
        PlatformPluginRegistry.register("myplatform", DummyExecutor)
        assert PlatformPluginRegistry.has("myplatform") is True
        assert PlatformPluginRegistry.has("nonexistent") is False

    def test_get_all_names(self):
        DummyExecutor = _make_concrete_subclass()
        PlatformPluginRegistry.register("alpha", DummyExecutor)
        PlatformPluginRegistry.register("beta", DummyExecutor)
        names = PlatformPluginRegistry.get_all_names()
        assert "alpha" in names
        assert "beta" in names

    def test_create_executor(self):
        DummyExecutor = _make_concrete_subclass()
        PlatformPluginRegistry.register("dummy", DummyExecutor)
        executor = PlatformPluginRegistry.create_executor("dummy")
        assert executor is not None
        assert executor.platform_name == "dummy"

    def test_create_executor_not_found(self):
        PlatformPluginRegistry._discovered = True
        executor = PlatformPluginRegistry.create_executor("nonexistent")
        assert executor is None

    def test_from_class_decorator(self):
        @PlatformPluginRegistry.from_class
        class MyExecutor(BasePlatformExecutor):
            platform_name = "my_custom"
            def visit(self, url): return True
            def get_tasks(self): return []
            def complete_task(self, task): return True

        assert PlatformPluginRegistry.get("my_custom") is MyExecutor

    def test_clear(self):
        DummyExecutor = _make_concrete_subclass()
        PlatformPluginRegistry.register("test", DummyExecutor)
        PlatformPluginRegistry.clear()
        PlatformPluginRegistry._discovered = True  # skip auto-discover
        assert PlatformPluginRegistry.get("test") is None

    def test_discover_sets_flag(self):
        PlatformPluginRegistry.discover()
        assert PlatformPluginRegistry._discovered is True


# ─── close() Tests ────────────────────────────────────────────

class TestExecutorClose:
    @patch.object(QuestNExecutor, "close")
    def test_questn_close(self, mock_close):
        executor = QuestNExecutor()
        executor.close()
        mock_close.assert_called_once()

    @patch.object(TaskOnExecutor, "close")
    def test_taskon_close(self, mock_close):
        executor = TaskOnExecutor()
        executor.close()
        mock_close.assert_called_once()

    @patch.object(IntractExecutor, "close")
    def test_intract_close(self, mock_close):
        executor = IntractExecutor()
        executor.close()
        mock_close.assert_called_once()

    @patch.object(Port3Executor, "close")
    def test_port3_close(self, mock_close):
        executor = Port3Executor()
        executor.close()
        mock_close.assert_called_once()

    @patch.object(GalxeExecutor, "close")
    def test_galxe_close(self, mock_close):
        executor = GalxeExecutor()
        executor.close()
        mock_close.assert_called_once()

    @patch.object(Layer3Executor, "close")
    def test_layer3_close(self, mock_close):
        executor = Layer3Executor()
        executor.close()
        mock_close.assert_called_once()
