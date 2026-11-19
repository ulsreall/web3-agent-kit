"""Zealy quest classification and parsing.

Quest type decides how a quest is handled — social quests open a tab, visit
quests navigate, everything else goes to a generic path — so a misclassified
quest is a quest that never completes. The parsing side turns a card into an
entry, and has to survive a card that is missing its title, XP or link.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from web3_agent_kit.airdrop.executor.zealy_exec import ZealyExecutor, ZealyQuestEntry, ZealyResult


def _executor() -> ZealyExecutor:
    return ZealyExecutor(SimpleNamespace())


def _quest(title: str, quest_type: str = "") -> ZealyQuestEntry:
    return ZealyQuestEntry(quest_id="1", title=title, quest_type=quest_type)


class TestClassification:
    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("Follow us on Twitter", "twitter_follow"),
            ("Retweet this post", "twitter_retweet"),
            ("Like the tweet on Twitter", "twitter_like"),
            ("Join our Discord", "discord_join"),
            ("Join Telegram", "telegram_join"),
            ("Subscribe on YouTube", "youtube_subscribe"),
            ("Visit the website", "visit_url"),
            ("Answer the quiz", "quiz"),
            ("Make a swap on-chain", "on_chain"),
            ("Do something else", "custom"),
        ],
    )
    def test_titles_map_to_types(self, title, expected):
        assert _executor()._classify_quest_type(title, None) == expected

    def test_classification_is_case_insensitive(self):
        assert _executor()._classify_quest_type("FOLLOW ON TWITTER", None) == "twitter_follow"


class TestPredicates:
    @pytest.mark.parametrize(
        "title", ["Follow on Twitter", "Retweet", "Join Discord", "Subscribe YouTube"]
    )
    def test_social_quests_are_social(self, title):
        assert _executor()._is_social_quest(_quest(title)) is True

    def test_quest_type_alone_can_mark_it_social(self):
        assert _executor()._is_social_quest(_quest("Whatever", "discord_join")) is True

    def test_plain_quest_is_not_social(self):
        assert _executor()._is_social_quest(_quest("Answer the quiz")) is False

    @pytest.mark.parametrize("title", ["Visit the site", "Read the docs", "Explore the app"])
    def test_visit_quests_are_detected(self, title):
        assert _executor()._is_visit_quest(_quest(title)) is True

    def test_quiz_is_not_a_visit(self):
        assert _executor()._is_visit_quest(_quest("Answer the quiz")) is False


class TestXpParsing:
    @pytest.mark.parametrize(("text", "expected"), [("150 XP", 150), ("1,250", 1250), ("0", 0)])
    def test_numbers_are_extracted(self, text, expected):
        assert _executor()._parse_xp(text) == expected

    @pytest.mark.parametrize("text", ["", "no reward", "XP"])
    def test_no_number_is_zero(self, text):
        assert _executor()._parse_xp(text) == 0


class TestCommunityExtraction:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://zealy.io/c/my-community", "my-community"),
            ("https://zealy.io/c/my-community/quest/123", "my-community"),
            ("https://zealy.io/community/other", "other"),
        ],
    )
    def test_slug_is_extracted(self, url, expected):
        assert _executor()._extract_community(url) == expected

    def test_bare_host_is_not_a_crash(self):
        assert _executor()._extract_community("https://zealy.io") == "unknown"


class _Card:
    """Minimal quest card: only the selectors the parser asks for exist."""

    def __init__(self, title=None, xp=None, completed=False, href=None, quest_id=None):
        self._title = title
        self._xp = xp
        self._completed = completed
        self._href = href
        self._quest_id = quest_id

    def query_selector(self, selector):
        if "quest-title" in selector or "QuestTitle" in selector or "h3" in selector:
            return SimpleNamespace(inner_text=lambda: self._title) if self._title else None
        if "xp" in selector or "reward" in selector or "points" in selector:
            return SimpleNamespace(inner_text=lambda: self._xp) if self._xp else None
        if "completed" in selector or "done" in selector:
            return object() if self._completed else None
        if "a[href]" in selector:
            return SimpleNamespace(get_attribute=lambda name: self._href) if self._href else None
        return None

    def get_attribute(self, name):
        return self._quest_id


class TestParseQuest:
    def test_full_card_is_parsed(self):
        card = _Card(title="Follow on Twitter", xp="120 XP", href="https://x.com/x", quest_id="q1")
        quest = _executor()._parse_quest(card, 0)
        assert quest.title == "Follow on Twitter"
        assert quest.xp_reward == 120
        assert quest.quest_type == "twitter_follow"
        assert quest.url == "https://x.com/x"
        assert quest.quest_id == "q1"
        assert quest.is_completed is False

    def test_card_without_title_gets_a_positional_name(self):
        assert _executor()._parse_quest(_Card(), 7).title == "Quest 7"

    def test_card_without_xp_scores_zero(self):
        assert _executor()._parse_quest(_Card(title="Visit site"), 1).xp_reward == 0

    def test_completed_badge_is_recorded(self):
        quest = _executor()._parse_quest(_Card(title="Visit site", completed=True), 0)
        assert quest.is_completed is True

    def test_quest_id_falls_back_to_the_index(self):
        assert _executor()._parse_quest(_Card(title="Visit site"), 3).quest_id == "3"

    def test_a_broken_card_returns_none(self):
        class Broken:
            def query_selector(self, selector):
                raise RuntimeError("detached")

        assert _executor()._parse_quest(Broken(), 0) is None


class TestLinksFallback:
    def _page(self, links):
        return SimpleNamespace(query_selector_all=lambda selector: links)

    def test_links_become_entries(self):
        executor = _executor()
        link = SimpleNamespace(inner_text=lambda: "Visit site", get_attribute=lambda n: "/quest/1")
        executor._page = self._page([link])
        quests = executor._parse_quests_from_links()
        assert quests[0].title == "Visit site"
        assert quests[0].url == "/quest/1"

    def test_links_without_text_are_skipped(self):
        executor = _executor()
        empty = SimpleNamespace(inner_text=lambda: "", get_attribute=lambda n: "/quest/1")
        executor._page = self._page([empty])
        assert executor._parse_quests_from_links() == []

    def test_no_page_returns_empty(self):
        assert _executor()._parse_quests_from_links() == []


class TestResultSummary:
    def test_success_rate_of_an_empty_result(self):
        assert ZealyResult(community="c", community_url="u").success_rate == 0.0

    def test_success_rate_counts_completed_against_total(self):
        result = ZealyResult(community="c", community_url="u", total_quests=4, completed_quests=1)
        assert result.success_rate == 0.25


class TestCompleteAll:
    def _executor(self, monkeypatch, quests, complete=True, visit=True):
        executor = ZealyExecutor(SimpleNamespace())
        monkeypatch.setattr(executor, "visit", lambda url: visit)
        monkeypatch.setattr(executor, "get_quests", lambda: quests)
        monkeypatch.setattr(executor, "complete_quest", lambda quest: complete)
        monkeypatch.setattr(executor, "_random_delay", lambda: None)
        return executor

    def _quest(self, title, xp=10, completed=False):
        from web3_agent_kit.airdrop.executor.zealy_exec import ZealyQuestEntry

        return ZealyQuestEntry(quest_id=title, title=title, xp_reward=xp, is_completed=completed)

    def test_a_failed_visit_stops_before_parsing(self, monkeypatch):
        result = self._executor(monkeypatch, [], visit=False).complete_all("https://zealy.io/c/c")
        assert "Failed to load" in result.errors[0]
        assert result.total_quests == 0

    def test_no_quests_is_reported(self, monkeypatch):
        result = self._executor(monkeypatch, []).complete_all("https://zealy.io/c/c")
        assert result.errors == ["No quests found"]

    def test_completed_quests_are_skipped(self, monkeypatch):
        quests = [self._quest("done", completed=True), self._quest("todo")]
        result = self._executor(monkeypatch, quests).complete_all("https://zealy.io/c/c")
        assert result.skipped_quests == 1

    def test_xp_is_only_credited_on_success(self, monkeypatch):
        quests = [self._quest("bad", xp=50), self._quest("ok", xp=7)]
        executor = ZealyExecutor(SimpleNamespace())
        monkeypatch.setattr(executor, "visit", lambda url: True)
        monkeypatch.setattr(executor, "get_quests", lambda: quests)
        monkeypatch.setattr(executor, "complete_quest", lambda quest: quest.title == "ok")
        monkeypatch.setattr(executor, "_random_delay", lambda: None)
        result = executor.complete_all("https://zealy.io/c/c")
        assert result.xp_earned == 7
        assert result.failed_quests == 1

    def test_the_tracker_hears_only_about_successes(self, monkeypatch):
        marked = []

        class Tracker:
            def mark_task_completed(self, task):
                marked.append(task.title)

        executor = ZealyExecutor(SimpleNamespace())
        monkeypatch.setattr(executor, "visit", lambda url: True)
        monkeypatch.setattr(executor, "get_quests", lambda: [self._quest("ok"), self._quest("no")])
        monkeypatch.setattr(executor, "complete_quest", lambda quest: quest.title == "ok")
        monkeypatch.setattr(executor, "_random_delay", lambda: None)
        executor.complete_all("https://zealy.io/c/c", tracker=Tracker())
        assert marked == ["ok"]

    def test_an_unexpected_error_is_captured(self, monkeypatch):
        executor = self._executor(monkeypatch, [])
        monkeypatch.setattr(executor, "visit", lambda url: (_ for _ in ()).throw(RuntimeError("x")))
        result = executor.complete_all("https://zealy.io/c/c")
        assert "x" in result.errors[0]
        assert result.elapsed_seconds is not None
