"""Registry discovery: built-ins, user plugins, and class selection.

A module's directory listing is alphabetical and includes names it merely
imported, so picking "the first subclass" can select a helper or a re-export and
register the wrong executor under a platform name.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from web3_agent_kit.airdrop.executor import plugin_registry
from web3_agent_kit.airdrop.executor.base_executor import BasePlatformExecutor
from web3_agent_kit.airdrop.executor.plugin_registry import PlatformPluginRegistry


class _Helper(BasePlatformExecutor):
    platform_name = "helper"


class _HelperExecutor(BasePlatformExecutor):
    platform_name = "wanted"


@pytest.fixture(autouse=True)
def clean_registry():
    PlatformPluginRegistry.clear()
    yield
    PlatformPluginRegistry.clear()


class TestFindClass:
    def test_the_matching_platform_name_wins_over_alphabetical_order(self):
        module = types.SimpleNamespace(
            AaaHelper=_Helper,
            ZzzOther=_HelperExecutor,
        )
        assert PlatformPluginRegistry._find_executor_class(module, "wanted") is _HelperExecutor

    def test_a_single_candidate_is_used_without_a_name_match(self):
        module = types.SimpleNamespace(Only=_Helper)
        assert PlatformPluginRegistry._find_executor_class(module, "other") is _Helper

    def test_no_candidate_is_none(self):
        assert PlatformPluginRegistry._find_executor_class(types.SimpleNamespace(), "x") is None

    def test_the_base_class_is_never_returned(self):
        module = types.SimpleNamespace(Base=BasePlatformExecutor)
        assert PlatformPluginRegistry._find_executor_class(module, "x") is None

    def test_the_naming_fallback_still_works(self):
        class WantedExecutor(BasePlatformExecutor):
            pass

        # Not a BasePlatformExecutor subclass in the module listing sense, so the
        # name fallback must carry it.

        module = types.SimpleNamespace()
        assert PlatformPluginRegistry._find_executor_class(module, "wanted") is None
        module2 = types.SimpleNamespace(wantedExecutor=WantedExecutor)
        assert PlatformPluginRegistry._find_executor_class(module2, "wanted") is WantedExecutor


class TestDiscovery:
    def test_builtins_are_registered_once(self):
        names = PlatformPluginRegistry.get_all_names()
        assert {"galxe", "zealy", "questn"} <= set(names)
        first = dict(PlatformPluginRegistry.list_all())
        PlatformPluginRegistry.discover()
        assert PlatformPluginRegistry.list_all() == first

    def test_has_and_get_respect_case(self):
        assert PlatformPluginRegistry.has("GALXE") is True
        assert PlatformPluginRegistry.get("galxe") is not None
        assert PlatformPluginRegistry.get("nope") is None

    def test_list_all_returns_a_copy(self):
        PlatformPluginRegistry.list_all().clear()
        assert "galxe" in PlatformPluginRegistry.list_all()

    def test_create_executor_builds_an_instance(self):
        executor = PlatformPluginRegistry.create_executor("galxe")
        assert executor is not None and executor.platform_name == "galxe"

    def test_create_executor_unknown_is_none(self):
        assert PlatformPluginRegistry.create_executor("nope") is None

    def test_register_and_from_class(self):
        PlatformPluginRegistry.register("helper", _Helper)
        assert PlatformPluginRegistry.has("helper") is True

        @PlatformPluginRegistry.from_class
        class Named(BasePlatformExecutor):
            platform_name = "named"

        assert PlatformPluginRegistry.has("named") is True


class TestUserPlugins:
    def test_a_plugin_file_is_loaded_and_registered(self, tmp_path, monkeypatch):
        plugins = tmp_path / "plugins"
        plugins.mkdir()
        (plugins / "mine.py").write_text(
            "from web3_agent_kit.airdrop.executor.base_executor import BasePlatformExecutor\n"
            "class MineExecutor(BasePlatformExecutor):\n"
            "    platform_name = 'mine'\n"
        )
        monkeypatch.setattr(plugin_registry, "USER_PLUGINS_DIR", plugins)
        PlatformPluginRegistry.clear()
        assert PlatformPluginRegistry.has("mine") is True

    def test_a_plugin_without_a_platform_name_uses_the_class_name(self, tmp_path, monkeypatch):
        plugins = tmp_path / "plugins"
        plugins.mkdir()
        (plugins / "anon.py").write_text(
            "from web3_agent_kit.airdrop.executor.base_executor import BasePlatformExecutor\n"
            "class AnonExecutor(BasePlatformExecutor):\n"
            "    pass\n"
        )
        monkeypatch.setattr(plugin_registry, "USER_PLUGINS_DIR", plugins)
        PlatformPluginRegistry.clear()
        assert PlatformPluginRegistry.has("anonexecutor") is True

    def test_a_broken_plugin_is_skipped_not_fatal(self, tmp_path, monkeypatch, caplog):
        plugins = tmp_path / "plugins"
        plugins.mkdir()
        (plugins / "broken.py").write_text("raise RuntimeError('boom')\n")
        monkeypatch.setattr(plugin_registry, "USER_PLUGINS_DIR", plugins)
        PlatformPluginRegistry.clear()
        with caplog.at_level("WARNING"):
            names = PlatformPluginRegistry.get_all_names()
        assert "boom" in caplog.text
        assert "galxe" in names

    def test_a_missing_directory_is_fine(self, monkeypatch):
        monkeypatch.setattr(plugin_registry, "USER_PLUGINS_DIR", Path("/tmp/no-such-plugins"))
        PlatformPluginRegistry.clear()
        assert "galxe" in PlatformPluginRegistry.get_all_names()

    def test_a_plugin_cannot_be_loaded_twice(self, tmp_path, monkeypatch):
        plugins = tmp_path / "plugins"
        plugins.mkdir()
        (plugins / "mine.py").write_text(
            "from web3_agent_kit.airdrop.executor.base_executor import BasePlatformExecutor\n"
            "class MineExecutor(BasePlatformExecutor):\n"
            "    platform_name = 'mine'\n"
        )
        monkeypatch.setattr(plugin_registry, "USER_PLUGINS_DIR", plugins)
        PlatformPluginRegistry.clear()
        PlatformPluginRegistry.discover()
        count = len(PlatformPluginRegistry.list_all())
        PlatformPluginRegistry.discover()
        assert len(PlatformPluginRegistry.list_all()) == count
        sys.modules.pop("user_plugin_mine", None)
