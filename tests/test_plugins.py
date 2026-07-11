"""Tests for Plugin System."""

import tempfile
import os

import pytest

from web3_agent_kit.plugins import Plugin, PluginMeta, PluginRegistry, PluginManager


# === Test Plugins ===

class SimplePlugin(Plugin):
    """A simple test plugin."""

    @property
    def meta(self) -> PluginMeta:
        return PluginMeta(
            name="simple-plugin",
            version="1.0.0",
            description="A simple test plugin",
            author="Test",
            hooks=["on_block"],
        )

    def setup(self, agent) -> None:
        self.agent = agent
        self.setup_called = True

    def execute(self, action: str, **kwargs) -> dict:
        if action == "ping":
            return {"pong": True}
        return {"error": f"Unknown: {action}"}

    def on_block(self, block_number: int) -> None:
        self.last_block = block_number

    def teardown(self) -> None:
        self.teardown_called = True


class AnotherPlugin(Plugin):
    """Another test plugin."""

    @property
    def meta(self) -> PluginMeta:
        return PluginMeta(
            name="another-plugin",
            version="2.0.0",
            description="Another test plugin",
            author="Test",
            hooks=["on_transaction"],
        )

    def setup(self, agent) -> None:
        self.agent = agent

    def execute(self, action: str, **kwargs) -> dict:
        return {"action": action, "kwargs": kwargs}

    def on_transaction(self, tx: dict) -> dict:
        tx["modified"] = True
        return tx


class BrokenPlugin(Plugin):
    """Plugin that fails on setup."""

    @property
    def meta(self) -> PluginMeta:
        return PluginMeta(
            name="broken-plugin",
            version="0.1.0",
            description="Broken plugin",
            author="Test",
        )

    def setup(self, agent) -> None:
        raise RuntimeError("Setup failed!")

    def execute(self, action: str, **kwargs) -> dict:
        raise NotImplementedError


# === Test PluginMeta ===

class TestPluginMeta:
    def test_creation(self):
        meta = PluginMeta(
            name="test",
            version="1.0.0",
            description="Test plugin",
            author="Author",
        )
        assert meta.name == "test"
        assert meta.version == "1.0.0"
        assert meta.requires == []
        assert meta.chain_specific == []
        assert meta.hooks == []

    def test_with_hooks(self):
        meta = PluginMeta(
            name="test",
            version="1.0.0",
            description="Test",
            author="Author",
            hooks=["on_block", "on_transaction"],
        )
        assert "on_block" in meta.hooks
        assert "on_transaction" in meta.hooks


# === Test PluginRegistry ===

class TestPluginRegistry:
    def test_register(self):
        registry = PluginRegistry()
        plugin = SimplePlugin()
        registry.register(plugin)

        assert registry.get("simple-plugin") is plugin

    def test_register_duplicate_raises(self):
        registry = PluginRegistry()
        registry.register(SimplePlugin())

        with pytest.raises(ValueError, match="already registered"):
            registry.register(SimplePlugin())

    def test_unregister(self):
        registry = PluginRegistry()
        plugin = SimplePlugin()
        registry.register(plugin)

        result = registry.unregister("simple-plugin")
        assert result is True
        assert registry.get("simple-plugin") is None
        assert hasattr(plugin, "teardown_called")

    def test_unregister_nonexistent(self):
        registry = PluginRegistry()
        result = registry.unregister("nonexistent")
        assert result is False

    def test_list_plugins(self):
        registry = PluginRegistry()
        registry.register(SimplePlugin())
        registry.register(AnotherPlugin())

        plugins = registry.list_plugins()
        assert len(plugins) == 2
        names = [p.name for p in plugins]
        assert "simple-plugin" in names
        assert "another-plugin" in names

    def test_setup_all(self):
        registry = PluginRegistry()
        plugin = SimplePlugin()
        registry.register(plugin)

        registry.setup_all(agent="mock_agent")
        assert plugin.setup_called is True
        assert plugin.agent == "mock_agent"

    def test_setup_all_handles_errors(self):
        registry = PluginRegistry()
        registry.register(SimplePlugin())
        registry.register(BrokenPlugin())

        # Should not raise, just print error
        registry.setup_all(agent="mock_agent")

    def test_teardown_all(self):
        registry = PluginRegistry()
        plugin = SimplePlugin()
        registry.register(plugin)
        registry.setup_all(agent="mock")

        registry.teardown_all()
        assert plugin.teardown_called is True

    def test_fire_hook(self):
        registry = PluginRegistry()
        plugin = SimplePlugin()
        registry.register(plugin)
        registry.setup_all(agent="mock")

        registry.fire_hook("on_block", block_number=123)
        assert plugin.last_block == 123

    def test_fire_hook_multiple_plugins(self):
        registry = PluginRegistry()
        p1 = SimplePlugin()
        p2 = AnotherPlugin()
        registry.register(p1)
        registry.register(p2)

        results = registry.fire_hook("on_transaction", tx={"value": 100})
        assert len(results) == 1  # Only AnotherPlugin has on_transaction hook
        assert results[0]["modified"] is True

    def test_discover_from_dir(self):
        """Test plugin discovery from directory."""
        registry = PluginRegistry()

        # Create a temporary plugin file
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_code = '''
from web3_agent_kit.plugins import Plugin, PluginMeta

class DirPlugin(Plugin):
    @property
    def meta(self):
        return PluginMeta(
            name="dir-plugin",
            version="1.0.0",
            description="Plugin from dir",
            author="Test",
        )

    def setup(self, agent):
        pass

    def execute(self, action, **kwargs):
        return {"from": "dir"}

def register_plugin():
    return DirPlugin()
'''
            plugin_path = os.path.join(tmpdir, "my_plugin.py")
            with open(plugin_path, "w") as f:
                f.write(plugin_code)

            loaded = registry.discover_from_dir(tmpdir)
            assert "dir-plugin" in loaded
            assert registry.get("dir-plugin") is not None

    def test_discover_from_empty_dir(self):
        registry = PluginRegistry()
        with tempfile.TemporaryDirectory() as tmpdir:
            loaded = registry.discover_from_dir(tmpdir)
            assert loaded == []

    def test_discover_nonexistent_dir(self):
        registry = PluginRegistry()
        loaded = registry.discover_from_dir("/nonexistent/path")
        assert loaded == []


# === Test PluginManager ===

class TestPluginManager:
    def test_execute(self):
        manager = PluginManager()
        manager.registry.register(SimplePlugin())

        result = manager.execute("simple-plugin", "ping")
        assert result == {"pong": True}

    def test_execute_nonexistent(self):
        manager = PluginManager()
        result = manager.execute("nonexistent", "action")
        assert "error" in result

    def test_list_plugins(self):
        manager = PluginManager()
        manager.registry.register(SimplePlugin())
        manager.registry.register(AnotherPlugin())

        plugins = manager.list_plugins()
        assert len(plugins) == 2

    def test_before_transaction(self):
        manager = PluginManager()
        manager.registry.register(AnotherPlugin())
        manager.setup_all(agent="mock")

        tx = {"value": 100}
        result = manager.before_transaction(tx)
        assert result["modified"] is True

    def test_load_dir(self):
        manager = PluginManager()
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_code = '''
from web3_agent_kit.plugins import Plugin, PluginMeta

class TestDirPlugin(Plugin):
    @property
    def meta(self):
        return PluginMeta(
            name="test-dir",
            version="1.0.0",
            description="Test",
            author="Test",
        )
    def setup(self, agent): pass
    def execute(self, action, **kwargs): return {}

def register_plugin():
    return TestDirPlugin()
'''
            with open(os.path.join(tmpdir, "test.py"), "w") as f:
                f.write(plugin_code)

            loaded = manager.load_dir(tmpdir)
            assert "test-dir" in loaded


# === Test Base Plugin ===

class TestBasePlugin:
    def test_execute_not_implemented(self):
        plugin = SimplePlugin()
        # SimplePlugin handles "ping", but not "unknown"
        result = plugin.execute("unknown")
        assert "error" in result

    def test_default_execute_raises(self):
        """Test that base Plugin.execute raises NotImplementedError."""
        plugin = BrokenPlugin()
        with pytest.raises(NotImplementedError):
            plugin.execute("anything")

    def test_default_teardown(self):
        """Test that default teardown doesn't raise."""
        plugin = AnotherPlugin()
        plugin.teardown()  # Should not raise

    def test_on_transaction_passthrough(self):
        """Test that default on_transaction returns tx unchanged."""
        plugin = SimplePlugin()
        tx = {"value": 100}
        result = plugin.on_transaction(tx)
        assert result == {"value": 100}
