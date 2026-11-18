"""Form field detection, matching and filling.

The filler is the product surface for airdrop forms, and its logic is DOM
plumbing that can be driven with a fake page. Two properties matter beyond
"it fills": a value must never land in the wrong box, and the browser must be
closed even when the page has no fields at all (the common failure).
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from web3_agent_kit.airdrop.form_filler import (
    FIELD_PATTERNS,
    FormField,
    FormFiller,
    FormProfile,
)

EMAIL = "someone@example.com"
WALLET = "0x" + "ab" * 20
TWITTER = "@someone"


def _profile() -> FormProfile:
    return FormProfile(name="A Name", email=EMAIL, wallet=WALLET, twitter=TWITTER)


class _El:
    def __init__(self, attrs=None, text="", visible=True, fail_fill=False):
        self._attrs = attrs or {}
        self._text = text
        self._visible = visible
        self._fail = fail_fill
        self.filled = None
        self.clicked = 0
        self.selected = None

    def get_attribute(self, name):
        return self._attrs.get(name)

    def inner_text(self):
        return self._text

    def is_visible(self):
        return self._visible

    def click(self):
        self.clicked += 1

    def fill(self, value):
        if self._fail:
            raise RuntimeError("fill refused")
        self.filled = value

    def select_option(self, label=None):
        self.selected = label


class _Page:
    def __init__(self, inputs=(), by_selector=None, labels=None):
        self._inputs = list(inputs)
        self._by_selector = by_selector or {}
        self._labels = labels or {}
        self.waits = 0
        self.goto_url = None
        self.screenshots = []

    def query_selector_all(self, selector):
        return self._inputs

    def query_selector(self, selector):
        if selector.startswith('label[for="'):
            key = selector.split('"')[1]
            return self._labels.get(key)
        return self._by_selector.get(selector)

    def goto(self, url, wait_until=None, timeout=None):
        self.goto_url = url

    def wait_for_timeout(self, ms):
        self.waits += 1

    def screenshot(self, path=None):
        self.screenshots.append(path)


class TestFieldDetection:
    def test_field_with_label_and_id(self):
        page = _Page(
            inputs=[_El({"id": "mail", "type": "email", "required": "required"})],
            labels={"mail": _El(text="Email address")},
        )
        fields = FormFiller(_profile())._detect_fields(page)
        assert fields[0].label == "Email address"
        assert fields[0].selector == "#mail"
        assert fields[0].required is True

    def test_field_without_label_falls_back_to_placeholder(self):
        page = _Page(inputs=[_El({"name": "wallet", "placeholder": "Your wallet"})])
        fields = FormFiller(_profile())._detect_fields(page)
        assert fields[0].label == "Your wallet"
        assert fields[0].selector == '[name="wallet"]'

    def test_field_without_name_or_id_uses_the_placeholder_selector(self):
        page = _Page(inputs=[_El({"placeholder": "Twitter handle"})])
        assert FormFiller(_profile())._detect_fields(page)[0].selector == (
            'input[placeholder="Twitter handle"]'
        )

    def test_a_broken_element_is_skipped_not_fatal(self):
        class Broken:
            def get_attribute(self, name):
                raise RuntimeError("detached")

        page = _Page(inputs=[Broken(), _El({"name": "email"})])
        assert len(FormFiller(_profile())._detect_fields(page)) == 1


class TestMatching:
    @pytest.mark.parametrize(
        ("label", "expected"),
        [
            ("Email address", EMAIL),
            ("Your wallet address", WALLET),
            ("Twitter handle", TWITTER),
        ],
    )
    def test_label_selects_the_right_value(self, label, expected):
        field = FormField(name="x", label=label, field_type="text", selector="#x")
        assert FormFiller(_profile())._match_field(field) == expected

    def test_unknown_field_matches_nothing(self):
        field = FormField(name="x", label="Favourite colour", field_type="text", selector="#x")
        assert FormFiller(_profile())._match_field(field) == ""

    def test_empty_profile_value_is_not_used(self):
        field = FormField(name="email", label="Email", field_type="text", selector="#x")
        assert FormFiller(FormProfile())._match_field(field) == ""

    def test_patterns_are_superset_of_the_profile_fields(self):
        assert {"name", "email", "wallet", "twitter"} <= set(FIELD_PATTERNS)


class TestFilling:
    def test_text_field_is_clicked_then_filled(self, monkeypatch):
        element = _El()
        page = _Page(by_selector={"#a": element})
        field = FormField(name="a", label="Email", field_type="text", selector="#a")
        assert FormFiller(_profile())._fill_field(page, field, EMAIL) is True
        assert element.filled == EMAIL
        assert element.clicked == 1

    def test_select_uses_select_option(self, monkeypatch):
        element = _El()
        page = _Page(by_selector={"#s": element})
        field = FormField(name="s", label="Country", field_type="select", selector="#s")
        assert FormFiller(_profile())._fill_field(page, field, "Indonesia") is True
        assert element.selected == "Indonesia"

    def test_missing_element_reports_false(self):
        field = FormField(name="a", label="Email", field_type="text", selector="#gone")
        assert FormFiller(_profile())._fill_field(_Page(), field, EMAIL) is False

    def test_fill_error_reports_false_rather_than_raising(self):
        page = _Page(by_selector={"#a": _El(fail_fill=True)})
        field = FormField(name="a", label="Email", field_type="text", selector="#a")
        assert FormFiller(_profile())._fill_field(page, field, EMAIL) is False


class TestSubmit:
    def test_first_visible_submit_button_is_clicked(self):
        hidden = _El(visible=False)
        visible = _El()
        page = _Page(by_selector={'button[type="submit"]': hidden, "#submit": visible})
        assert FormFiller(_profile())._submit_form(page) is True
        assert visible.clicked == 1
        assert hidden.clicked == 0

    def test_no_button_reports_false(self):
        assert FormFiller(_profile())._submit_form(_Page()) is False


class _Browser:
    def __init__(self, page):
        self.page = page
        self.closed = False
        self.user_agent = None

    def new_context(self, user_agent=None):
        self.user_agent = user_agent
        return SimpleNamespace(new_page=lambda: self.page)

    def close(self):
        self.closed = True


@pytest.fixture
def fake_playwright(monkeypatch):
    holder = {}

    def install(page):
        browser = _Browser(page)

        class Chromium:
            @staticmethod
            def launch(headless=True):
                return browser

        class SyncPlaywright:
            def __enter__(self):
                return SimpleNamespace(chromium=Chromium)

            def __exit__(self, *exc):
                return False

        sync_playwright = SyncPlaywright
        module = SimpleNamespace(sync_playwright=sync_playwright)
        monkeypatch.setitem(sys.modules, "playwright", SimpleNamespace(sync_api=module))
        monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
        holder["browser"] = browser
        return browser

    return install


class TestFillRun:
    def test_fills_and_submits_then_closes_the_browser(self, fake_playwright):
        email_el = _El({"name": "email", "type": "email"})
        submit_el = _El()
        page = _Page(
            inputs=[email_el],
            by_selector={'[name="email"]': email_el, 'button[type="submit"]': submit_el},
        )
        browser = fake_playwright(page)

        result = FormFiller(_profile()).fill("https://form.test")
        assert result.success is True
        assert result.fields_filled == 1
        assert email_el.filled == EMAIL
        assert page.goto_url == "https://form.test"
        assert browser.closed is True

    def test_no_fields_still_closes_the_browser(self, fake_playwright):
        page = _Page()
        browser = fake_playwright(page)
        result = FormFiller(_profile()).fill("https://form.test")
        assert result.error == "No form fields detected"
        assert result.submitted is False
        # The early return used to skip browser.close() and leak chromium.
        assert browser.closed is True

    def test_unmatched_fields_are_counted_as_skipped(self, fake_playwright):
        page = _Page(inputs=[_El({"name": "colour", "placeholder": "Colour"})])
        browser = fake_playwright(page)
        result = FormFiller(_profile()).fill("https://form.test", submit=False)
        assert result.fields_skipped == 1
        assert result.fields_filled == 0
        assert browser.closed is True

    def test_submit_can_be_disabled(self, fake_playwright):
        page = _Page(inputs=[_El({"name": "email"})], by_selector={'button[type="submit"]': _El()})
        fake_playwright(page)
        result = FormFiller(_profile()).fill("https://form.test", submit=False)
        assert result.submitted is False
        assert result.success is False

    def test_screenshot_is_recorded_when_requested(self, fake_playwright):
        page = _Page(inputs=[_El({"name": "email"})])
        fake_playwright(page)
        result = FormFiller(_profile()).fill("https://form.test", submit=False)
        assert result.screenshot_path
        assert page.screenshots == [result.screenshot_path]

    def test_missing_playwright_is_reported(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "playwright", None)
        result = FormFiller(_profile()).fill("https://form.test")
        assert "Playwright" in result.error
