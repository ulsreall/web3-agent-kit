"""Platform plugin registry — auto-discovery and registration.

Provides a registry for platform executors that supports both built-in
and user-defined plugins. Auto-discovers executors from the executor
directory and user plugins directory.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Type

from .base_executor import BasePlatformExecutor

logger = logging.getLogger(__name__)

# User plugins directory
USER_PLUGINS_DIR = Path.home() / ".web3-agent-kit" / "plugins"


class PlatformPluginRegistry:
    """Registry for platform executors with auto-discovery.

    Supports:
        - Built-in executor registration
        - User plugin auto-discovery from ~/.web3-agent-kit/plugins/
        - Decorator-based registration
        - Dynamic loading

    Example::

        # Register a custom executor
        @PlatformPluginRegistry.from_class
        class MyCustomExecutor(BasePlatformExecutor):
            platform_name = "my_custom"
            ...

        # Or register manually
        PlatformPluginRegistry.register("my_custom", MyCustomExecutor)

        # Get an executor
        executor_cls = PlatformPluginRegistry.get("galxe")
        executor = executor_cls(config)
    """

    _registry: Dict[str, Type[BasePlatformExecutor]] = {}
    _discovered: bool = False

    @classmethod
    def register(
        cls,
        name: str,
        executor_class: Type[BasePlatformExecutor],
    ) -> None:
        """Register a platform executor.

        Args:
            name: Platform name (used for lookup).
            executor_class: The executor class to register.

        Raises:
            TypeError: If executor_class is not a BasePlatformExecutor subclass.
        """
        if not (
            isinstance(executor_class, type)
            and issubclass(executor_class, BasePlatformExecutor)
        ):
            raise TypeError(
                f"{executor_class} must be a subclass of BasePlatformExecutor"
            )

        cls._registry[name.lower()] = executor_class
        logger.info(f"Registered platform executor: {name}")

    @classmethod
    def get(cls, name: str) -> Optional[Type[BasePlatformExecutor]]:
        """Get an executor class by name.

        Args:
            name: Platform name.

        Returns:
            The executor class, or None if not found.
        """
        # Auto-discover if not yet done
        if not cls._discovered:
            cls.discover()

        return cls._registry.get(name.lower())

    @classmethod
    def list_all(cls) -> Dict[str, Type[BasePlatformExecutor]]:
        """List all registered platform executors.

        Returns:
            Dict mapping platform names to executor classes.
        """
        if not cls._discovered:
            cls.discover()

        return dict(cls._registry)

    @classmethod
    def discover(cls) -> None:
        """Auto-discover platform executors.

        Discovers from:
            1. Built-in executors in src/airdrop/executor/
            2. User plugins in ~/.web3-agent-kit/plugins/*.py
        """
        if cls._discovered:
            return

        cls._discover_builtin()
        cls._discover_user_plugins()
        cls._discovered = True

        logger.info(f"Discovered {len(cls._registry)} platform executors")

    @classmethod
    def _discover_builtin(cls) -> None:
        """Discover built-in executors from the executor package."""
        builtin_modules = {
            "questn": ".questn",
            "taskon": ".taskon",
            "intract": ".intract_exec",
            "port3": ".port3_exec",
            "galxe": ".galxe_exec",
            "layer3": ".layer3_exec",
            "gleam": ".gleam_exec",
            "zealy": ".zealy_exec",
        }

        for name, module_path in builtin_modules.items():
            try:
                # Import the module
                module = importlib.import_module(
                    module_path,
                    package="src.airdrop.executor",
                )

                # Find executor classes in the module
                executor_class = cls._find_executor_class(module, name)
                if executor_class:
                    cls._registry[name] = executor_class
                    logger.debug(f"Discovered built-in executor: {name}")

            except ImportError as e:
                logger.debug(f"Could not import {module_path}: {e}")
            except Exception as e:
                logger.debug(f"Error discovering {name}: {e}")

    @classmethod
    def _discover_user_plugins(cls) -> None:
        """Discover user plugins from ~/.web3-agent-kit/plugins/."""
        if not USER_PLUGINS_DIR.exists():
            logger.debug(f"User plugins directory not found: {USER_PLUGINS_DIR}")
            return

        for plugin_file in USER_PLUGINS_DIR.glob("*.py"):
            try:
                cls._load_plugin_file(plugin_file)
            except Exception as e:
                logger.warning(f"Failed to load plugin {plugin_file}: {e}")

    @classmethod
    def _load_plugin_file(cls, plugin_path: Path) -> None:
        """Load a plugin from a Python file.

        Args:
            plugin_path: Path to the plugin Python file.
        """
        module_name = f"user_plugin_{plugin_path.stem}"

        spec = importlib.util.spec_from_file_location(module_name, plugin_path)
        if not spec or not spec.loader:
            return

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
        except Exception as e:
            logger.warning(f"Failed to execute plugin {plugin_path}: {e}")
            return

        # Find executor classes
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BasePlatformExecutor)
                and attr is not BasePlatformExecutor
            ):
                name = getattr(attr, "platform_name", attr_name.lower())
                cls._registry[name] = attr
                logger.info(f"Discovered user plugin: {name} from {plugin_path}")

    @classmethod
    def _find_executor_class(
        cls,
        module: Any,
        fallback_name: str,
    ) -> Optional[Type[BasePlatformExecutor]]:
        """Find the executor class in a module.

        Args:
            module: The imported module.
            fallback_name: Fallback platform name if not found.

        Returns:
            The executor class, or None.
        """
        # Look for classes that extend BasePlatformExecutor
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BasePlatformExecutor)
                and attr is not BasePlatformExecutor
            ):
                return attr

        # Fallback: look for common naming patterns
        for class_name in [
            f"{fallback_name.title()}Executor",
            f"{fallback_name.upper()}Executor",
            f"{fallback_name.capitalize()}Executor",
        ]:
            attr = getattr(module, class_name, None)
            if attr and isinstance(attr, type):
                return attr

        return None

    @classmethod
    def from_class(cls, executor_class: Type[BasePlatformExecutor]) -> Type[BasePlatformExecutor]:
        """Decorator to register an executor class.

        Args:
            executor_class: The executor class to register.

        Returns:
            The executor class (unchanged).

        Example::

            @PlatformPluginRegistry.from_class
            class MyExecutor(BasePlatformExecutor):
                platform_name = "my_platform"
                ...
        """
        name = getattr(executor_class, "platform_name", executor_class.__name__.lower())
        cls.register(name, executor_class)
        return executor_class

    @classmethod
    def clear(cls) -> None:
        """Clear the registry (for testing)."""
        cls._registry.clear()
        cls._discovered = False

    @classmethod
    def has(cls, name: str) -> bool:
        """Check if a platform is registered.

        Args:
            name: Platform name.

        Returns:
            True if registered.
        """
        if not cls._discovered:
            cls.discover()
        return name.lower() in cls._registry

    @classmethod
    def get_all_names(cls) -> list[str]:
        """Get all registered platform names.

        Returns:
            List of platform names.
        """
        if not cls._discovered:
            cls.discover()
        return list(cls._registry.keys())

    @classmethod
    def create_executor(
        cls,
        name: str,
        config: Optional[Any] = None,
    ) -> Optional[BasePlatformExecutor]:
        """Create an executor instance by name.

        Args:
            name: Platform name.
            config: Optional executor configuration.

        Returns:
            An executor instance, or None if not found.
        """
        executor_class = cls.get(name)
        if executor_class:
            return executor_class(config=config)
        return None


# Auto-register built-in executors on import
def _auto_register() -> None:
    """Auto-register all built-in executors."""
    PlatformPluginRegistry.discover()
