"""Gleam task classification and entry parsing.

The classification decides which handler runs, and a handler for the wrong
network opens the wrong tab and burns the task. Parsing has to survive the
decorative bits of a real entry: an empty title, a ``javascript:`` link, no
action button at all.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from web3_agent_kit.airdrop.executor.gleam_exec import (
    GleamExecutor,
    GleamResult,
    GleamTaskType,
)


def _executor() -> GleamExecutor:
    return GleamExecutor(SimpleNamespace())


class TestClassification:
    @pytest.mark.parametrize(
        ("title", "method", "url", "expected"),
        [
            ("Follow us on Twitter", "", "", GleamTaskType.TWITTER_FOLLOW),
            ("Retweet the post", "", "", GleamTaskType.TWITTER_RETWEET),
            ("Like on Twitter", "", "", GleamTaskType.TWITTER_LIKE),
            ("Tweet about us", "", "", GleamTaskType.TWITTER_TWEET),
            ("Subscribe on YouTube", "", "", GleamTaskType.YOUTUBE_SUBSCRIBE),
            ("Join Discord", "", "", GleamTaskType.DISCORD_JOIN),
            ("Join Telegram", "", "", GleamTaskType.TELEGRAM_JOIN),
            ("Visit the page", "", "", GleamTaskType.VISIT_URL),
            ("Refer a friend", "", "", GleamTaskType.REFERRAL),
            ("Something else", "", "", GleamTaskType.CUSTOM_ACTION),
        ],
    )
    def test_text_selects_the_handler(self, title, method, url, expected):
        assert _executor()._classify_task(title, method, url) == expected

    def test_follow_beats_a_bare_tweet_mention(self):
        assert (
            _executor()._classify_task("Follow and tweet on Twitter", "", "")
            is GleamTaskType.TWITTER_FOLLOW
        )

    def test_url_alone_can_make_it_telegram_or_visit(self):
        assert _executor()._classify_task("Join", "", "https://t.me/x") is (
            GleamTaskType.TELEGRAM_JOIN
        )
        # A bare URL is not enough on its own; Gleam marks those with method=url.
        assert _executor()._classify_task("Join", "url", "https://example.com") is (
            GleamTaskType.VISIT_URL
        )

    def test_follow_on_x_is_a_twitter_follow(self):
        assert _executor()._classify_task("Follow on X", "", "https://x.com/team") is (
            GleamTaskType.TWITTER_FOLLOW
        )

    def test_classification_is_case_insensitive(self):
        assert _executor()._classify_task("JOIN DISCORD", "", "") is GleamTaskType.DISCORD_JOIN


class _Entry:
    def __init__(self, title=None, completed=False, href=None, entry_id=None, button=None):
        self._title = title
        self._completed = completed
        self._href = href
        self._entry_id = entry_id
        self._button = button

    def query_selector(self, selector):
        if "title" in selector:
            return SimpleNamespace(inner_text=lambda: self._title) if self._title else None
        if "completed" in selector or "done" in selector or "check" in selector:
            return object() if self._completed else None
        if selector.startswith("a[href"):
            return SimpleNamespace(get_attribute=lambda name: self._href) if self._href else None
        if self._button and selector == "button":
            return object()
        return None

    def get_attribute(self, name):
        if name == "data-entry-id":
            return self._entry_id
        return ""


class TestParseEntry:
    def test_full_entry_is_parsed(self):
        entry = _Entry(title="Follow on Twitter", href="https://x.com/x", entry_id="e1")
        task = _executor()._parse_entry(entry, 0)
        assert task.title == "Follow on Twitter"
        assert task.task_type is GleamTaskType.TWITTER_FOLLOW
        assert task.url == "https://x.com/x"
        assert task.entry_id == "e1"

    def test_missing_title_gets_a_positional_name(self):
        assert _executor()._parse_entry(_Entry(), 4).title == "Task 4"

    def test_javascript_and_anchor_links_are_dropped(self):
        for href in ("javascript:void(0)", "#panel"):
            assert _executor()._parse_entry(_Entry(title="Visit", href=href), 0).url == ""

    def test_completed_badge_is_recorded(self):
        assert _executor()._parse_entry(_Entry(title="Visit", completed=True), 0).is_completed

    def test_entry_id_falls_back_to_the_index(self):
        assert _executor()._parse_entry(_Entry(title="Visit"), 6).entry_id == "6"

    def test_button_selector_is_found(self):
        task = _executor()._parse_entry(_Entry(title="Visit", button=True), 0)
        assert task.selector == "button"

    def test_a_broken_entry_returns_none(self):
        class Broken:
            def query_selector(self, selector):
                raise RuntimeError("detached")

        assert _executor()._parse_entry(Broken(), 0) is None


class TestResultSummary:
    def test_empty_result(self):
        result = GleamResult(campaign_url="u", campaign_id="c")
        assert result.success_rate == 0.0
        assert result.is_fully_completed is False

    def test_partial_result_is_not_fully_completed(self):
        result = GleamResult(campaign_url="u", campaign_id="c", total_tasks=4, completed_tasks=1)
        assert result.success_rate == 0.25
        assert result.is_fully_completed is False

    def test_all_done_is_fully_completed(self):
        result = GleamResult(campaign_url="u", campaign_id="c", total_tasks=2, completed_tasks=2)
        assert result.is_fully_completed is True
