class _QR:
    def __init__(self, payload=None, status=200):
        self._p = payload or {}
        self.status_code = status

    def json(self):
        return self._p


def _qn(get=None, post=None):
    from web3_agent_kit.airdrop.executor.questn import QuestNExecutor

    executor = QuestNExecutor()
    executor._campaign_id = "camp1"
    sent = {"get": [], "post": []}

    def _g(url, **kw):
        sent["get"].append((url, kw))
        return _QR(get or {})

    def _p(url, **kw):
        sent["post"].append((url, kw))
        return _QR(post or {})

    executor._get = _g  # type: ignore[method-assign]
    executor._post = _p  # type: ignore[method-assign]
    return executor, sent


def _qtask(quest_id="q1", title="t", task_type="custom"):
    from web3_agent_kit.airdrop.executor.questn import QuestNTask

    task = QuestNTask(task_id=quest_id, title=title, quest_id=quest_id, quest_type=task_type)
    return task


class TestQuestNParse:
    def test_a_null_type_keeps_the_task(self):
        task = _qn()[0]._parse_task({"id": "1", "type": None}, 0)
        assert task is not None and task.task_type == "custom"

    def test_a_null_title_falls_back(self):
        assert _qn()[0]._parse_task({"id": "1", "title": None}, 1).title == "Task 1"

    def test_required_defaults_true(self):
        assert _qn()[0]._parse_task({"id": "1"}, 0).required is True

    def test_a_null_step_list_is_empty(self):
        executor, _ = _qn(get={"tasks": None})
        assert executor.get_tasks() == []


class TestQuestNFlow:
    def test_visit_returns_true_on_200(self):
        executor, sent = _qn(get={"title": "T"})
        assert executor.visit("https://questn.xyz/quest/abc") is True
        assert sent["get"][0][1]["headers"]["Referer"].endswith("/quest/abc")

    def test_visit_is_true_when_the_api_fails(self):
        executor, _ = _qn()

        def boom(*a, **k):
            raise RuntimeError("down")

        executor._get = boom  # type: ignore[method-assign]
        assert executor.visit("https://questn.xyz/quest/abc") is True

    def test_tasks_are_collected(self):
        executor, _ = _qn(get={"tasks": [{"id": "1", "title": "a"}]})
        assert [t.title for t in executor.get_tasks()] == ["a"]

    def test_no_campaign_is_an_empty_list(self):
        executor, sent = _qn()
        executor._campaign_id = None
        assert executor.get_tasks() == []
        assert sent["get"] == []

    def test_a_throwing_listing_is_an_empty_list(self):
        executor, _ = _qn()

        def boom(*a, **k):
            raise RuntimeError("down")

        executor._get = boom  # type: ignore[method-assign]
        assert executor.get_tasks() == []

    def test_a_completed_task_needs_no_request(self):
        executor, sent = _qn()
        task = _qtask()
        task.is_completed = True
        assert executor.complete_task(task) is True
        assert sent["post"] == []

    def test_success_requires_the_action_and_the_verification(self):
        executor, sent = _qn(post={"success": True, "verified": True})
        task = _qtask()
        assert executor.complete_task(task) is True
        assert task.is_completed is True
        assert [u.split("/")[-1] for u, _ in sent["post"]] == ["complete", "verify"]

    def test_a_failed_action_skips_verification(self):
        executor, sent = _qn(post={"success": False})
        task = _qtask()
        assert executor.complete_task(task) is False
        assert len(sent["post"]) == 1
        assert task.is_completed is False

    def test_a_failed_verification_leaves_the_task_open(self):
        executor, _ = _qn(post={"success": True, "verified": False})
        task = _qtask()
        assert executor.complete_task(task) is False
        assert task.is_completed is False

    def test_a_throwing_verification_is_assumed_successful(self):
        # Optimistic by design: the action already went through.
        executor, _ = _qn(post={"success": True, "verified": True})
        calls = []

        def _p(url, **kw):
            calls.append(url)
            if url.endswith("/verify"):
                raise RuntimeError("down")
            return _QR({"success": True})

        executor._post = _p  # type: ignore[method-assign]
        task = _qtask()
        assert executor.complete_task(task) is True
        assert task.is_completed is True

    def test_the_handlers_send_their_own_action(self):
        for task_type, expected in [
            ("twitter_follow", "twitter_follow"),
            ("twitter_retweet", "twitter_retweet"),
            ("twitter_like", "twitter_like"),
            ("discord_join", "discord_join"),
            ("telegram_join", "telegram_join"),
            ("visit_url", "visit_url"),
            ("custom", "complete"),
        ]:
            executor, sent = _qn(post={"success": True, "verified": True})
            executor.complete_task(_qtask(task_type=task_type))
            assert sent["post"][0][1]["json"]["action"] == expected

    def test_a_quiz_reads_the_questions_first(self):
        executor, sent = _qn(
            get={"questions": [{"id": 1, "options": ["a", "b"], "correctAnswer": "b"}]},
            post={"success": True, "verified": True},
        )
        executor.complete_task(_qtask(task_type="quiz"))
        assert sent["get"][0][0].endswith("/quiz")
        assert sent["post"][0][1]["json"]["answers"] == {"1": "b"}

    def test_a_quiz_falls_back_to_the_first_option(self):
        executor, sent = _qn(
            get={"questions": [{"id": 2, "options": ["a"]}]}, post={"success": True}
        )
        executor.complete_task(_qtask(task_type="quiz"))
        assert sent["post"][0][1]["json"]["answers"] == {"2": "a"}

    def test_a_quiz_without_questions_still_submits(self):
        executor, sent = _qn(post={"success": True, "verified": True})
        executor.complete_task(_qtask(task_type="quiz"))
        assert sent["post"][0][1]["json"] == {"action": "quiz", "answers": {}}

    def test_a_broken_quiz_read_still_submits(self):
        executor, sent = _qn(post={"success": True, "verified": True})

        def _g(url, **kw):
            raise RuntimeError("down")

        executor._get = _g  # type: ignore[method-assign]
        executor.complete_task(_qtask(task_type="quiz"))
        assert sent["post"][0][1]["json"] == {"action": "quiz"}

    def test_close_clears_the_quests(self):
        executor, _ = _qn()
        executor._quests = [_qtask()]
        executor.close()
        assert executor._quests == []
