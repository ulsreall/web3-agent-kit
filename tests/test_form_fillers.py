"""The Typeform and Google Form fillers, against a scripted Playwright.

Both open a real chromium in production; here the browser is faked so the control
flow, the counters and the submit rules are what is under test.
"""

from __future__ import annotations

import sys
import types

import pytest

from web3_agent_kit.airdrop.form_filler import FormFiller, FormProfile


class _El:
    def __init__(self, text="", visible=True, fail=False):
        self._text = text
        self._visible = visible
        self._fail = fail
        self.filled = None
        self.clicked = 0

    def inner_text(self):
        return self._text

    def is_visible(self):
        return self._visible

    def fill(self, value):
        if self._fail:
            raise RuntimeError("detached")
        self.filled = value

    def click(self):
        if self._fail:
            raise RuntimeError("detached")
        self.clicked += 1


class _Page:
    def __init__(self, selectors=None, all_selectors=None, questions=None):
        self.selectors = selectors or {}
        self.all_selectors = all_selectors or {}
        self.questions = questions or []
        self.goto_calls = []
        self.shots = []
        self.waits = 0

    def goto(self, url, **kw):
        self.goto_calls.append((url, kw))

    def wait_for_timeout(self, ms):
        self.waits += 1

    def query_selector(self, selector):
        return self.selectors.get(selector)

    def query_selector_all(self, selector):
        return self.all_selectors.get(selector, [])

    def screenshot(self, path):
        self.shots.append(path)


class _Browser:
    def __init__(self, page):
        self.page = page
        self.closed = False
        self.context_kwargs = None

    def new_context(self, **kw):
        self.context_kwargs = kw
        return types.SimpleNamespace(new_page=lambda: self.page)

    def close(self):
        self.closed = True


@pytest.fixture
def browser_factory(monkeypatch):
    made = []

    def _make(page):
        browser = _Browser(page)
        made.append(browser)

        class _Chromium:
            @staticmethod
            def launch(headless=True):
                browser.headless = headless
                return browser

        module = types.SimpleNamespace(chromium=_Chromium())

        class _Ctx:
            def __enter__(self):
                return module

            def __exit__(self, *a):
                return False

        monkeypatch.setitem(
            sys.modules,
            "playwright.sync_api",
            types.SimpleNamespace(sync_playwright=lambda: _Ctx()),
        )
        return browser

    return _make


def _filler(profile=None) -> FormFiller:
    profile = profile or FormProfile(
        name="Ada",
        email="ada@example.com",
        twitter="@ada",
        telegram="@ada",
        discord="ada#1",
        wallet="0xabc",
        custom={"message": "gm"},
    )
    return FormFiller(profile)


class TestTypeform:
    def test_steps_fill_until_no_question_remains(self, browser_factory):
        submit = _El()
        page = _Page(
            selectors={
                'button[data-qa="submit-button"], button:has-text("Submit"), button:has-text("Done")': submit
            }
        )
        browser = browser_factory(page)
        filler = _filler()
        questions = iter(["What is your email?", ""])
        monkeypatch_ok = []

        filler._detect_typeform_question = lambda p: next(questions)  # type: ignore[method-assign]
        filler._match_typeform_field = lambda q: "ada@example.com" if "email" in q else ""  # type: ignore[method-assign]
        filler._fill_typeform_field = lambda p, v: monkeypatch_ok.append(v) or True  # type: ignore[method-assign]

        result = filler.fill_typeform("https://t.example/f")
        assert result.fields_found == 1
        assert result.fields_filled == 1
        assert result.submitted is True and result.success is True
        assert browser.closed is True

    def test_an_unmatched_step_is_counted_as_skipped(self, browser_factory):
        page = _Page()
        browser_factory(page)
        filler = _filler()
        questions = iter(["Favorite chain?", ""])
        filler._detect_typeform_question = lambda p: next(questions)  # type: ignore[method-assign]
        filler._match_typeform_field = lambda q: ""  # type: ignore[method-assign]

        result = filler.fill_typeform("https://t.example/f", submit=False)
        assert (result.fields_found, result.fields_skipped) == (1, 1)
        assert result.submitted is False

    def test_a_broken_fill_aborts_into_an_error(self, browser_factory):
        page = _Page()
        browser = browser_factory(page)
        filler = _filler()
        filler._detect_typeform_question = lambda p: "email"  # type: ignore[method-assign]
        filler._match_typeform_field = lambda q: "ada@example.com"  # type: ignore[method-assign]

        def boom(*a):
            raise RuntimeError("fill broke")

        filler._fill_typeform_field = boom  # type: ignore[method-assign]
        result = filler.fill_typeform("https://t.example/f")
        assert result.error == "fill broke"
        assert browser.closed is True

    def test_the_browser_is_headless(self, browser_factory):
        browser = browser_factory(_Page())
        _filler().fill_typeform("https://t.example/f", submit=False)
        assert browser.headless is True

    def test_a_missing_playwright_is_reported(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
        result = _filler().fill_typeform("https://t.example/f")
        assert "Playwright not installed" in result.error


class TestGoogleForm:
    def _question(self, label, kind="input", value="Ada"):
        if kind == "input":
            return types.SimpleNamespace(
                query_selector=lambda sel: _El() if "input" in sel else None,
                _label=label,
                query_selector_label=lambda: _El(label),
            )
        return types.SimpleNamespace(
            query_selector=lambda sel: _El() if "listbox" in sel else None,
        )

    def _q(self, label, kind="input"):
        class _Q:
            def __init__(self):
                self.label_el = _El(label)

            def query_selector(self, sel):
                if "heading" in sel:
                    return self.label_el
                if kind == "input" and ("input" in sel or "textarea" in sel):
                    return _El()
                if kind == "select" and "listbox" in sel:
                    return _El()
                return None

        return _Q()

    def test_questions_are_filled_and_counted(self, browser_factory):
        page = _Page(all_selectors={'div[role="listitem"]': [self._q("Name"), self._q("Email")]})
        browser_factory(page)
        result = _filler().fill_google_form("https://docs.example/f", submit=False)
        assert (result.fields_found, result.fields_filled, result.fields_skipped) == (2, 2, 0)

    def test_an_unsupported_question_is_counted_as_skipped(self, browser_factory):
        # Nothing to fill and nothing to skip used to leave the counters short.
        page = _Page(
            all_selectors={'div[role="listitem"]': [self._q("Grid?", "none"), self._q("Name")]}
        )
        browser_factory(page)
        result = _filler().fill_google_form("https://docs.example/f", submit=False)
        assert result.fields_found == 2
        assert result.fields_filled + result.fields_skipped == 2
        assert any("unsupported" in d for d in result.details)

    def test_an_unknown_question_is_skipped(self, browser_factory):
        page = _Page(all_selectors={'div[role="listitem"]': [self._q("Which planet?")]})
        browser_factory(page)
        result = _filler().fill_google_form("https://docs.example/f", submit=False)
        assert result.fields_skipped == 1

    def test_submit_marks_success_only_with_a_button(self, browser_factory):
        page = _Page(all_selectors={'div[role="listitem"]': []})
        browser_factory(page)
        result = _filler().fill_google_form("https://docs.example/f")
        assert result.submitted is False and result.success is False

    def test_a_submit_button_is_clicked(self, browser_factory):
        button = _El()
        page = _Page(
            all_selectors={'div[role="listitem"]': []},
            selectors={'div[role="button"]:has-text("Submit")': button},
        )
        browser_factory(page)
        result = _filler().fill_google_form("https://docs.example/f")
        assert result.success is True and button.clicked == 1

    def test_a_broken_dropdown_aborts_into_an_error(self, browser_factory):
        page = _Page(all_selectors={'div[role="listitem"]': [self._q("Name", "select")]})
        browser_factory(page)
        filler = _filler()

        def boom(*a):
            raise RuntimeError("dropdown broke")

        filler._fill_google_dropdown = boom  # type: ignore[method-assign]
        result = filler.fill_google_form("https://docs.example/f")
        assert result.error == "dropdown broke"
