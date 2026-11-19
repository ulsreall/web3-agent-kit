class _TR:
    def __init__(self, payload=None, status=200):
        self._p = payload or {}
        self.status_code = status

    def json(self):
        return self._p


def _tn(get=None, post=None):
    from web3_agent_kit.airdrop.executor.taskon import TaskOnExecutor

    executor = TaskOnExecutor()
    executor._campaign_id = "camp1"
    sent = {"get": [], "post": []}

    def _g(url, **kw):
        sent["get"].append((url, kw))
        return _TR(get or {})

    def _p(url, **kw):
        sent["post"].append((url, kw))
        return _TR(post or {})

    executor._get = _g  # type: ignore[method-assign]
    executor._post = _p  # type: ignore[method-assign]
    return executor, sent


def _ttask(task_type="custom", done=False):
    from web3_agent_kit.airdrop.executor.taskon import TaskOnTask

    task = TaskOnTask(task_id="t1", title="t", task_type=task_type)
    task.is_completed = done
    return task


class TestTaskOnParse:
    def test_a_null_type_keeps_the_task(self):
        task = _tn()[0]._parse_task({"id": "1", "type": None}, 0)
        assert task is not None and task.task_type == "custom"

    def test_a_null_title_falls_back(self):
        assert _tn()[0]._parse_task({"id": "1", "title": None}, 1).title == "Task 1"

    def test_the_raw_type_is_preserved(self):
        assert _tn()[0]._parse_task({"id": "1", "type": "weird"}, 0).task_type_raw == "weird"

    def test_a_null_task_list_is_empty(self):
        assert _tn(get={"tasks": None})[0].get_tasks() == []

    def test_a_null_data_envelope_is_empty(self):
        assert _tn(get={"data": None})[0].get_tasks() == []


class TestTaskOnFlow:
    def test_visit_stores_the_campaign(self):
        executor, sent = _tn(get={"name": "C"})
        assert executor.visit("https://taskon.xyz/campaign/abc") is True
        assert executor._campaign_data == {"name": "C"}
        assert sent["get"][0][0].endswith("/campaign/abc")

    def test_a_null_campaign_name_does_not_raise(self):
        executor, _ = _tn(get={"name": None, "title": None})
        assert executor.visit("https://taskon.xyz/campaign/abc") is True

    def test_visit_is_true_when_the_api_fails(self):
        executor, _ = _tn()

        def boom(*a, **k):
            raise RuntimeError("down")

        executor._get = boom  # type: ignore[method-assign]
        assert executor.visit("https://taskon.xyz/campaign/abc") is True

    def test_tasks_are_collected(self):
        executor, _ = _tn(get={"tasks": [{"id": "1", "title": "a"}]})
        assert [t.title for t in executor.get_tasks()] == ["a"]

    def test_without_a_campaign_no_request_is_made(self):
        executor, sent = _tn()
        executor._campaign_id = None
        assert executor.get_tasks() == []
        assert sent["get"] == []

    def test_a_throwing_listing_is_an_empty_list(self):
        executor, _ = _tn()

        def boom(*a, **k):
            raise RuntimeError("down")

        executor._get = boom  # type: ignore[method-assign]
        assert executor.get_tasks() == []

    def test_a_completed_task_needs_no_request(self):
        executor, sent = _tn()
        assert executor.complete_task(_ttask(done=True)) is True
        assert sent["post"] == []

    def test_success_marks_the_task_and_sends_the_action_data(self):
        executor, sent = _tn(post={"success": True})
        task = _ttask()
        task.action_data = {"x": 1}
        assert executor.complete_task(task) is True
        assert task.is_completed is True
        assert sent["post"][0][1]["json"] == {
            "campaign_id": "camp1",
            "task_type": "custom",
            "action_data": {"x": 1},
        }

    def test_status_completed_counts(self):
        assert _tn(post={"status": "completed"})[0].complete_task(_ttask()) is True

    def test_a_failure_stays_open(self):
        task = _ttask()
        assert _tn(post={"success": False})[0].complete_task(task) is False
        assert task.is_completed is False

    def test_a_throwing_transport_is_false(self):
        executor, _ = _tn()

        def boom(*a, **k):
            raise RuntimeError("down")

        executor._post = boom  # type: ignore[method-assign]
        assert executor.complete_task(_ttask()) is False

    def test_close_clears_the_campaign(self):
        executor, _ = _tn()
        executor._campaign_data = {"a": 1}
        executor.close()
        assert executor._campaign_data is None
