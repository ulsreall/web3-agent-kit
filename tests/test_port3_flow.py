class _PR:
    def __init__(self, payload=None, status=200):
        self._p = payload or {}
        self.status_code = status

    def json(self):
        return self._p


def _p3(get=None, post=None):
    from web3_agent_kit.airdrop.executor.port3_exec import Port3Executor

    executor = Port3Executor()
    executor._campaign_id = "camp1"
    sent = {"get": [], "post": []}

    def _g(url, **kw):
        sent["get"].append((url, kw))
        return _PR(get or {})

    def _p(url, **kw):
        sent["post"].append((url, kw))
        return _PR(post or {})

    executor._get = _g  # type: ignore[method-assign]
    executor._post = _p  # type: ignore[method-assign]
    return executor, sent


def _ptask(done=False):
    from web3_agent_kit.airdrop.executor.port3_exec import Port3Task

    task = Port3Task(task_id="t1", title="t")
    task.is_completed = done
    return task


class TestPort3Parse:
    def test_a_null_type_keeps_the_task(self):
        task = _p3()[0]._parse_task({"id": "1", "type": None}, 0)
        assert task is not None and task.task_type == "custom"

    def test_a_null_title_falls_back(self):
        assert _p3()[0]._parse_task({"id": "1", "title": None}, 1).title == "Task 1"

    def test_the_chain_id_reaches_the_metadata(self):
        task = _p3()[0]._parse_task({"id": "1", "chainId": 56}, 0)
        assert task.chain_id == 56 and task.metadata["chain_id"] == 56

    def test_a_null_task_list_is_empty(self):
        assert _p3(get={"tasks": None})[0].get_tasks() == []


class TestPort3Flow:
    def test_visit_returns_true_on_200(self):
        executor, sent = _p3(get={"title": "T"})
        assert executor.visit("https://port3.io/quest/abc") is True
        assert sent["get"][0][0].endswith("/quest/abc")

    def test_visit_is_true_when_the_api_fails(self):
        executor, _ = _p3()

        def boom(*a, **k):
            raise RuntimeError("down")

        executor._get = boom  # type: ignore[method-assign]
        assert executor.visit("https://port3.io/quest/abc") is True

    def test_tasks_are_collected(self):
        executor, _ = _p3(get={"tasks": [{"id": "1", "title": "a"}]})
        assert [t.title for t in executor.get_tasks()] == ["a"]

    def test_a_token_becomes_a_bearer_header_on_both_calls(self):
        executor, sent = _p3(get={"tasks": []})
        executor._auth_token = "tok"
        executor.get_tasks()
        assert sent["get"][0][1]["headers"]["Authorization"] == "Bearer tok"

    def test_without_a_campaign_no_request_is_made(self):
        executor, sent = _p3()
        executor._campaign_id = None
        assert executor.get_tasks() == []
        assert sent["get"] == []

    def test_a_throwing_listing_is_an_empty_list(self):
        executor, _ = _p3()

        def boom(*a, **k):
            raise RuntimeError("down")

        executor._get = boom  # type: ignore[method-assign]
        assert executor.get_tasks() == []

    def test_a_completed_task_needs_no_request(self):
        executor, sent = _p3()
        assert executor.complete_task(_ptask(done=True)) is True
        assert sent["post"] == []

    def test_success_marks_the_task(self):
        executor, sent = _p3(post={"success": True})
        task = _ptask()
        assert executor.complete_task(task) is True
        assert task.is_completed is True
        assert sent["post"][0][1]["json"]["quest_id"] == "camp1"

    def test_status_completed_counts(self):
        assert _p3(post={"status": "completed"})[0].complete_task(_ptask()) is True

    def test_a_failure_stays_open(self):
        task = _ptask()
        assert _p3(post={"success": False})[0].complete_task(task) is False
        assert task.is_completed is False

    def test_a_throwing_transport_is_false(self):
        executor, _ = _p3()

        def boom(*a, **k):
            raise RuntimeError("down")

        executor._post = boom  # type: ignore[method-assign]
        assert executor.complete_task(_ptask()) is False

    def test_a_token_authenticates(self):
        executor, _ = _p3()
        assert executor.login({"token": "t"}) is True and executor._authenticated

    def test_no_credentials_is_false(self):
        assert _p3()[0].login({}) is False

    def test_close_clears_the_token(self):
        executor, _ = _p3()
        executor._auth_token = "t"
        executor.close()
        assert executor._auth_token is None
