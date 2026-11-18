"""Whitelist grinder platform routing and bulk bookkeeping.

Routing decides which filler runs, and the bulk loop decides what gets skipped
and how the counters land. Both are cheap to get wrong and expensive to notice:
a misrouted URL fills the wrong form, and a wrong counter reports a failed
application as a success.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from web3_agent_kit.airdrop.wl_grinder import WLGrinder, WLJob, WLProfile, WLResult

WALLET = "0x" + "ab" * 20


def _grinder() -> WLGrinder:
    return WLGrinder(WLProfile(wallet=WALLET, email="me@example.com"))


class TestPlatformDetection:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://form.typeform.com/to/abc", "typeform"),
            ("https://forms.gle/xyz", "google_form"),
            ("https://docs.google.com/forms/d/e/1", "google_form"),
            ("https://premint.xyz/collection", "premint"),
            ("https://gleam.io/campaign", "gleam"),
            ("https://own.ly/drop", "ownly"),
            ("https://raffall.com/x", "raffall"),
            ("https://example.com/form", "generic"),
        ],
    )
    def test_url_selects_the_platform(self, url, expected):
        assert _grinder()._detect_platform(url) == expected

    def test_detection_is_case_insensitive(self):
        assert _grinder()._detect_platform("HTTPS://TYPEFORM.COM/to/a") == "typeform"


class TestApplyRouting:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("url", "method"),
        [
            ("https://form.typeform.com/to/abc", "_apply_typeform"),
            ("https://forms.gle/x", "_apply_google_form"),
            ("https://gleam.io/x", "_apply_gleam"),
            ("https://example.com/x", "_apply_generic"),
        ],
    )
    async def test_url_reaches_the_matching_filler(self, url, method, monkeypatch):
        grinder = _grinder()
        called = {}

        def fake(self_, url_, result):
            called["method"] = method
            result.success = True
            return result

        monkeypatch.setattr(WLGrinder, method, fake)
        result = await grinder.apply(url)
        assert called["method"] == method
        assert result.success is True
        assert url in grinder.get_applied()

    @pytest.mark.asyncio
    async def test_a_failed_application_is_not_recorded(self, monkeypatch):
        grinder = _grinder()
        monkeypatch.setattr(
            WLGrinder,
            "_apply_generic",
            lambda self_, url_, result: result,
        )
        result = await grinder.apply("https://example.com/x")
        assert result.success is False
        assert grinder.get_applied() == []

    @pytest.mark.asyncio
    async def test_a_throwing_filler_becomes_an_error_result(self, monkeypatch):
        def boom(self_, url_, result):
            raise RuntimeError("playwright died")

        monkeypatch.setattr(WLGrinder, "_apply_generic", boom)
        result = await _grinder().apply("https://example.com/x")
        assert "playwright died" in result.error
        assert result.success is False


class TestBulk:
    def _grinder_with(self, monkeypatch, outcomes):
        grinder = _grinder()

        async def fake_apply(self_, url):
            ok = outcomes[url]
            result = WLResult(url=url, success=ok, error="" if ok else "nope")
            if ok:
                self_._applied_urls.add(url)
            return result

        monkeypatch.setattr(WLGrinder, "apply", fake_apply)
        return grinder

    @pytest.mark.asyncio
    async def test_counters_split_success_from_failure(self, monkeypatch):
        grinder = self._grinder_with(monkeypatch, {"a": True, "b": False})
        job = await grinder.apply_bulk(["a", "b"], delay=0)
        assert (job.success, job.failed, job.skipped) == (1, 1, 0)
        assert job.total == 2

    @pytest.mark.asyncio
    async def test_already_applied_urls_are_skipped(self, monkeypatch):
        grinder = self._grinder_with(monkeypatch, {"a": True})
        grinder._applied_urls.add("a")
        job = await grinder.apply_bulk(["a"], delay=0)
        assert job.skipped == 1
        assert job.success == 0
        assert job.results[0].error == "Already applied"

    @pytest.mark.asyncio
    async def test_skip_can_be_disabled(self, monkeypatch):
        grinder = self._grinder_with(monkeypatch, {"a": True})
        grinder._applied_urls.add("a")
        job = await grinder.apply_bulk(["a"], delay=0, skip_existing=False)
        assert job.skipped == 0
        assert job.success == 1

    @pytest.mark.asyncio
    async def test_apply_bulk_and_async_apply_bulk_agree(self, monkeypatch):
        grinder = self._grinder_with(monkeypatch, {"a": True, "b": True})
        first = await grinder.apply_bulk(["a", "b"], delay=0)
        grinder._applied_urls.clear()
        second = await grinder.async_apply_bulk(["a", "b"], delay=0)
        assert (first.success, first.total) == (second.success, second.total)


class TestExport:
    def test_results_are_written_as_json(self, tmp_path):
        job = WLJob(urls=["u"], total=1, success=1)
        job.results.append(WLResult(url="u", success=True))
        path = tmp_path / "out.json"
        _grinder().export_results(job, str(path))
        payload = json.loads(path.read_text())
        assert payload["summary"]["success"] == 1
        assert payload["summary"]["success_rate"] == "100%"
        assert payload["results"][0]["url"] == "u"

    def test_job_success_rate(self):
        assert WLJob(urls=[], total=0).success_rate == 0.0
        assert WLJob(urls=["u"], total=2, success=1).success_rate == 0.5


class TestHandlers:
    """The handlers convert a filler result into a WLResult."""

    def _fake_filler(self, monkeypatch, *, success, submitted, details=None):
        from web3_agent_kit.airdrop import form_filler

        class FakeFiller:
            def __init__(self, profile):
                self.profile = profile

            def _result(self):
                return SimpleNamespace(success=success, submitted=submitted, details=details or [])

            def fill(self, url):
                return self._result()

            def fill_typeform(self, url):
                return self._result()

            def fill_google_form(self, url):
                return self._result()

        monkeypatch.setattr(form_filler, "FormFiller", FakeFiller)

    def test_profile_fields_reach_the_filler(self, monkeypatch):
        from web3_agent_kit.airdrop import form_filler

        seen = {}

        class Spy:
            def __init__(self, profile):
                seen.update(profile.__dict__)

            def fill(self, url):
                return SimpleNamespace(success=True, submitted=True, details=[])

        monkeypatch.setattr(form_filler, "FormFiller", Spy)
        _grinder()._apply_generic("u", WLResult(url="u"))
        assert seen["wallet"] == WALLET
        assert seen["email"] == "me@example.com"

    @pytest.mark.parametrize("method", ["_apply_typeform", "_apply_google_form", "_apply_generic"])
    def test_success_and_submission_are_copied(self, method, monkeypatch):
        self._fake_filler(monkeypatch, success=True, submitted=True, details=["ok"])
        result = getattr(_grinder(), method)("u", WLResult(url="u"))
        assert result.success is True
        assert result.applied is True
        assert result.details == ["ok"]

    @pytest.mark.parametrize("method", ["_apply_typeform", "_apply_google_form", "_apply_generic"])
    def test_filler_failure_is_not_a_success(self, method, monkeypatch):
        self._fake_filler(monkeypatch, success=False, submitted=False)
        result = getattr(_grinder(), method)("u", WLResult(url="u"))
        assert result.success is False
        assert result.applied is False

    @pytest.mark.parametrize("method", ["_apply_typeform", "_apply_google_form", "_apply_generic"])
    def test_a_throwing_filler_becomes_an_error(self, method, monkeypatch):
        from web3_agent_kit.airdrop import form_filler

        class Boom:
            def __init__(self, profile):
                pass

            def __getattr__(self, name):
                raise RuntimeError("no browser")

        monkeypatch.setattr(form_filler, "FormFiller", Boom)
        result = getattr(_grinder(), method)("u", WLResult(url="u"))
        assert "no browser" in result.error

    def test_gleam_needs_more_than_half_the_tasks(self, monkeypatch):
        from web3_agent_kit.airdrop.executor import browser as browser_mod
        from web3_agent_kit.airdrop.executor import gleam_exec

        class FakeBrowser:
            def __init__(self, config):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class FakeExecutor:
            def __init__(self, browser):
                pass

            def complete_all(self, url):
                return SimpleNamespace(success_rate=0.4, completed_tasks=2, total_tasks=5)

        monkeypatch.setattr(gleam_exec, "GleamExecutor", FakeExecutor)
        monkeypatch.setattr(browser_mod, "BrowserConfig", lambda **kw: None)
        monkeypatch.setattr(browser_mod, "BrowserManager", FakeBrowser)
        result = _grinder()._apply_gleam("u", WLResult(url="u"))
        assert result.success is False
        assert result.applied is True
        assert result.details == ["Completed: 2/5"]

    def test_gleam_majority_is_a_success(self, monkeypatch):
        from web3_agent_kit.airdrop.executor import browser as browser_mod
        from web3_agent_kit.airdrop.executor import gleam_exec

        class FakeBrowser:
            def __init__(self, config):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class FakeExecutor:
            def __init__(self, browser):
                pass

            def complete_all(self, url):
                return SimpleNamespace(success_rate=1.0, completed_tasks=3, total_tasks=3)

        monkeypatch.setattr(gleam_exec, "GleamExecutor", FakeExecutor)
        monkeypatch.setattr(browser_mod, "BrowserConfig", lambda **kw: None)
        monkeypatch.setattr(browser_mod, "BrowserManager", FakeBrowser)
        assert _grinder()._apply_gleam("u", WLResult(url="u")).success is True
