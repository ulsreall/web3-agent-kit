"""Plugin System — Extend web3-agent-kit with community plugins."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import json
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class PluginMeta:
    """Plugin metadata."""
    name: str                     # Unique plugin name (e.g. "uniswap-trader")
    version: str                  # Semver (e.g. "1.0.0")
    description: str              # What the plugin does
    author: str                   # Plugin author
    requires: list[str] = field(default_factory=list)  # Dependencies
    chain_specific: list[str] = field(default_factory=list)  # Chains supported (empty = all)
    hooks: list[str] = field(default_factory=list)  # Hooks this plugin registers


class Plugin(ABC):
    """Base class for all web3-agent-kit plugins.

    To create a plugin:

    1. Subclass `Plugin`
    2. Implement `meta` property and `setup()` method
    3. Optionally implement `execute()` and hooks
    4. Package as a Python module

    Example::

        from web3_agent_kit.plugins import Plugin, PluginMeta

        class MyPlugin(Plugin):
            @property
            def meta(self) -> PluginMeta:
                return PluginMeta(
                    name="my-plugin",
                    version="1.0.0",
                    description="Does cool things",
                    author="Your Name",
                )

            def setup(self, agent):
                self.agent = agent

            def execute(self, action: str, **kwargs) -> dict:
                if action == "greet":
                    return {"message": f"Hello from {self.meta.name}!"}
                return {"error": f"Unknown action: {action}"}
    """

    @property
    @abstractmethod
    def meta(self) -> PluginMeta:
        """Return plugin metadata."""
        ...

    @abstractmethod
    def setup(self, agent: Any) -> None:
        """Initialize the plugin with agent context.

        Called once when the plugin is loaded. Use this to store
        references to the agent, wallet, chain, etc.
        """
        ...

    def execute(self, action: str, **kwargs) -> dict:
        """Execute a plugin action.

        Override this to handle custom actions. Default raises NotImplementedError.
        """
        raise NotImplementedError(
            f"Plugin '{self.meta.name}' does not implement execute()"
        )

    def teardown(self) -> None:
        """Cleanup when plugin is unloaded. Override if needed."""
        pass

    # === Hook methods (optional overrides) ===

    def on_transaction(self, tx: dict) -> dict:
        """Called before a transaction is sent. Can modify or reject.

        Args:
            tx: Transaction dict.

        Returns:
            Modified transaction dict, or raise to reject.
        """
        return tx

    def on_transaction_complete(self, tx: dict, result: dict) -> None:
        """Called after a transaction completes."""
        pass

    def on_block(self, block_number: int) -> None:
        """Called on each new block (if subscribed)."""
        pass

    def on_price_update(self, token: str, price: float) -> None:
        """Called when a price update is received."""
        pass

    def on_startup(self) -> None:
        """Called when the agent starts."""
        pass

    def on_shutdown(self) -> None:
        """Called when the agent shuts down."""
        pass


class PluginRegistry:
    """Central registry for discovering and managing plugins.

    Example::

        registry = PluginRegistry()
        registry.register(MyPlugin())
        registry.discover_from_dir("./plugins")

        plugin = registry.get("my-plugin")
        result = plugin.execute("greet")
    """

    def __init__(self):
        self._plugins: dict[str, Plugin] = {}
        self._hooks: dict[str, list[Plugin]] = {}  # hook_name -> [plugins]

    def register(self, plugin: Plugin) -> None:
        """Register a plugin instance.

        Args:
            plugin: Plugin instance to register.

        Raises:
            ValueError: If plugin name already registered.
        """
        name = plugin.meta.name
        if name in self._plugins:
            raise ValueError(f"Plugin '{name}' is already registered")

        self._plugins[name] = plugin

        # Index hooks
        for hook in plugin.meta.hooks:
            self._hooks.setdefault(hook, []).append(plugin)

    def unregister(self, name: str) -> bool:
        """Unregister a plugin by name.

        Args:
            name: Plugin name to remove.

        Returns:
            True if removed, False if not found.
        """
        plugin = self._plugins.pop(name, None)
        if plugin is None:
            return False

        # Remove from hooks
        for hook_plugins in self._hooks.values():
            while plugin in hook_plugins:
                hook_plugins.remove(plugin)

        plugin.teardown()
        return True

    def get(self, name: str) -> Optional[Plugin]:
        """Get a plugin by name."""
        return self._plugins.get(name)

    def list_plugins(self) -> list[PluginMeta]:
        """List all registered plugins."""
        return [p.meta for p in self._plugins.values()]

    def setup_all(self, agent: Any) -> None:
        """Setup all registered plugins with agent context.

        Args:
            agent: The Agent instance to pass to each plugin.
        """
        for plugin in self._plugins.values():
            try:
                plugin.setup(agent)
            except Exception as e:
                print(f"[PluginRegistry] Failed to setup '{plugin.meta.name}': {e}")

    def teardown_all(self) -> None:
        """Teardown all plugins."""
        for plugin in self._plugins.values():
            try:
                plugin.teardown()
            except Exception:
                pass

    def fire_hook(self, hook_name: str, **kwargs) -> list[Any]:
        """Fire a hook and collect results from all registered plugins.

        Args:
            hook_name: Name of the hook to fire.
            **kwargs: Arguments to pass to the hook method.

        Returns:
            List of results from each plugin that handles the hook.
        """
        results = []
        for plugin in self._hooks.get(hook_name, []):
            method = getattr(plugin, hook_name, None)
            if method:
                try:
                    result = method(**kwargs)
                    results.append(result)
                except Exception as e:
                    results.append({"error": str(e), "plugin": plugin.meta.name})
        return results

    def discover_from_dir(self, directory: str) -> list[str]:
        """Discover and load plugins from a directory.

        Each plugin should be a Python file or package with a
        `register_plugin()` function that returns a Plugin instance.

        Args:
            directory: Path to the plugins directory.

        Returns:
            List of plugin names that were loaded.
        """
        loaded = []
        plugin_dir = Path(directory)

        if not plugin_dir.exists():
            return loaded

        for item in plugin_dir.iterdir():
            if item.name.startswith("_"):
                continue

            try:
                plugin = self._load_plugin_from_path(item)
                if plugin:
                    self.register(plugin)
                    loaded.append(plugin.meta.name)
            except Exception as e:
                print(f"[PluginRegistry] Failed to load '{item}': {e}")

        return loaded

    def discover_from_entry_points(self, group: str = "web3_agent_kit.plugins") -> list[str]:
        """Discover plugins from Python entry points.

        Package authors can register plugins via entry_points in setup.py:

            setup(
                ...
                entry_points={
                    "web3_agent_kit.plugins": [
                        "my_plugin = my_package.plugin:register_plugin",
                    ],
                },
            )

        Args:
            group: Entry point group name.

        Returns:
            List of plugin names that were loaded.
        """
        loaded = []

        if sys.version_info >= (3, 10):
            eps = importlib.metadata.entry_points(group=group)
        else:
            import pkg_resources
            eps = pkg_resources.iter_entry_points(group)

        for ep in eps:
            try:
                factory = ep.load()
                plugin = factory()
                if isinstance(plugin, Plugin):
                    self.register(plugin)
                    loaded.append(plugin.meta.name)
            except Exception as e:
                print(f"[PluginRegistry] Failed to load entry point '{ep.name}': {e}")

        return loaded

    def _load_plugin_from_path(self, path: Path) -> Optional[Plugin]:
        """Load a plugin from a file or directory."""
        if path.is_file() and path.suffix == ".py":
            return self._load_from_module(path)
        elif path.is_dir():
            init_file = path / "__init__.py"
            if init_file.exists():
                return self._load_from_module(init_file)
        return None

    def _load_from_module(self, path: Path) -> Optional[Plugin]:
        """Load a plugin module and call register_plugin()."""
        spec = importlib.util.spec_from_file_location(
            f"web3_plugin_{path.stem}",
            str(path),
        )
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Look for register_plugin() function
        register_fn = getattr(module, "register_plugin", None)
        if register_fn and callable(register_fn):
            result = register_fn()
            if isinstance(result, Plugin):
                return result

        # Look for Plugin subclasses
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, Plugin)
                and obj is not Plugin
                and not inspect.isabstract(obj)
            ):
                return obj()

        return None


class PluginManager:
    """High-level plugin management with lifecycle hooks.

    Wraps PluginRegistry and adds convenience methods for
    the Agent to call during execution.

    Example::

        manager = PluginManager()
        manager.load_dir("./plugins")
        manager.setup_all(agent)

        # In agent loop:
        manager.before_transaction(tx)
        manager.after_transaction(tx, result)
    """

    def __init__(self, registry: Optional[PluginRegistry] = None):
        self.registry = registry or PluginRegistry()
        self._loaded_dirs: list[str] = []

    def load_dir(self, directory: str) -> list[str]:
        """Load plugins from directory."""
        loaded = self.registry.discover_from_dir(directory)
        self._loaded_dirs.append(directory)
        return loaded

    def load_entry_points(self) -> list[str]:
        """Load plugins from Python entry points."""
        return self.registry.discover_from_entry_points()

    def setup_all(self, agent: Any) -> None:
        """Setup all plugins."""
        self.registry.setup_all(agent)

    def teardown_all(self) -> None:
        """Teardown all plugins."""
        self.registry.teardown_all()

    def before_transaction(self, tx: dict) -> dict:
        """Fire on_transaction hook before sending."""
        results = self.registry.fire_hook("on_transaction", tx=tx)
        # Last plugin's modified tx wins
        for result in results:
            if isinstance(result, dict) and "error" not in result:
                tx = result
        return tx

    def after_transaction(self, tx: dict, result: dict) -> None:
        """Fire on_transaction_complete hook."""
        self.registry.fire_hook("on_transaction_complete", tx=tx, result=result)

    def on_block(self, block_number: int) -> None:
        """Fire on_block hook."""
        self.registry.fire_hook("on_block", block_number=block_number)

    def on_price_update(self, token: str, price: float) -> None:
        """Fire on_price_update hook."""
        self.registry.fire_hook("on_price_update", token=token, price=price)

    def execute(self, plugin_name: str, action: str, **kwargs) -> dict:
        """Execute a specific plugin action.

        Args:
            plugin_name: Name of the plugin.
            action: Action to execute.
            **kwargs: Action arguments.

        Returns:
            Result dict from the plugin.
        """
        plugin = self.registry.get(plugin_name)
        if plugin is None:
            return {"error": f"Plugin '{plugin_name}' not found"}
        return plugin.execute(action, **kwargs)

    def list_plugins(self) -> list[dict]:
        """List all loaded plugins with metadata."""
        return [
            {
                "name": m.name,
                "version": m.version,
                "description": m.description,
                "author": m.author,
                "hooks": m.hooks,
            }
            for m in self.registry.list_plugins()
        ]
