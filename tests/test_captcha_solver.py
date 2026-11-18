"""CAPTCHA solver request shapes, polling and error handling.

The solver is the one place an API key and a paid task are in play, so the
tests pin what is actually sent: task type, payload keys, the poll contract and
every path that must raise instead of returning an empty token.
"""

from __future__ import annotations

import pytest
import requests

from web3_agent_kit.airdrop.executor.captcha_solver import (
    CaptchaConfig,
    CaptchaProvider,
    CaptchaSolver,
    CaptchaSolvingError,
)

KEY = "test-key"
URL = "https://example.com/form"
SITE_KEY = "6Le-site-key"


class _Resp:
    def __init__(self, payload, status=200, body_error=None):
        self._payload = payload
        self._status = status
        self._body_error = body_error

    def raise_for_status(self):
        if self._status >= 400:
            raise requests.HTTPError(f"HTTP {self._status}")

    def json(self):
        if self._body_error:
            raise self._body_error
        return self._payload


class _Session:
    """Replays a queue of responses and records every request."""

    def __init__(self, *responses):
        self._queue = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self._queue.pop(0)

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self._queue.pop(0)


def _solver(
    *responses, provider=CaptchaProvider.ANTICAPTCHA, key=KEY
) -> tuple[CaptchaSolver, _Session]:
    solver = CaptchaSolver(
        CaptchaConfig(provider=provider, api_key=key, timeout=1, poll_interval=0)
    )
    session = _Session(*responses)
    solver.session = session
    return solver, session


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(
        "web3_agent_kit.airdrop.executor.captcha_solver.time.sleep", lambda _s: None
    )
    # A frozen-enough clock so the poll loop runs a bounded number of iterations.
    ticks = iter(range(0, 10000))
    monkeypatch.setattr(
        "web3_agent_kit.airdrop.executor.captcha_solver.time.time", lambda: next(ticks) * 0.1
    )


class TestConfig:
    def test_key_comes_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("ANTICAPTCHA_API_KEY", "from-env")
        solver = CaptchaSolver(CaptchaConfig())
        assert solver.config.api_key == "from-env"

    def test_explicit_key_wins_over_the_environment(self, monkeypatch):
        monkeypatch.setenv("ANTICAPTCHA_API_KEY", "from-env")
        assert CaptchaSolver(CaptchaConfig(api_key=KEY)).config.api_key == KEY

    def test_missing_key_only_warns_at_construction(self, monkeypatch):
        monkeypatch.delenv("ANTICAPTCHA_API_KEY", raising=False)
        assert CaptchaSolver(CaptchaConfig()).config.api_key is None

    def test_two_captcha_uses_https(self):
        assert CaptchaSolver.TWOCAPTCHA_API.startswith("https://")


class TestAnticaptcha:
    def test_recaptcha_v2_payload(self):
        solver, session = _solver(
            _Resp({"errorId": 0, "taskId": 7}),
            _Resp({"errorId": 0, "status": "ready", "solution": {"gRecaptchaResponse": "tok"}}),
        )
        assert solver.solve_recaptcha_v2(SITE_KEY, URL) == "tok"
        payload = session.calls[0][1]["json"]
        assert payload["task"]["type"] == "RecaptchaV2TaskProxyless"
        assert payload["task"]["websiteKey"] == SITE_KEY
        assert "isInvisible" not in payload["task"]

    def test_invisible_flag_is_sent_as_a_string(self):
        solver, session = _solver(
            _Resp({"errorId": 0, "taskId": 7}),
            _Resp({"errorId": 0, "status": "ready", "solution": {"token": "tok"}}),
        )
        solver.solve_recaptcha_v2(SITE_KEY, URL, invisible=True)
        assert session.calls[0][1]["json"]["task"]["isInvisible"] == "true"

    def test_v3_sends_action_and_score(self):
        solver, session = _solver(
            _Resp({"errorId": 0, "taskId": 7}),
            _Resp({"errorId": 0, "status": "ready", "solution": {"token": "tok"}}),
        )
        solver.solve_recaptcha_v3(SITE_KEY, URL, action="login", min_score=0.5)
        task = session.calls[0][1]["json"]["task"]
        assert task["type"] == "RecaptchaV3TaskProxyless"
        assert task["pageAction"] == "login"
        assert task["minScore"] == 0.5

    def test_hcaptcha_payload(self):
        solver, session = _solver(
            _Resp({"errorId": 0, "taskId": 7}),
            _Resp({"errorId": 0, "status": "ready", "solution": {"token": "tok"}}),
        )
        assert solver.solve_hcaptcha(SITE_KEY, URL) == "tok"
        assert session.calls[0][1]["json"]["task"]["type"] == "HCaptchaTaskProxyless"

    def test_turnstile_payload(self):
        solver, session = _solver(
            _Resp({"errorId": 0, "taskId": 7}),
            _Resp({"errorId": 0, "status": "ready", "solution": {"token": "tok"}}),
        )
        assert solver.solve_turnstile(SITE_KEY, URL) == "tok"
        assert session.calls[0][1]["json"]["task"]["type"] == "TurnstileTaskProxyless"

    def test_geetest_solution_dict_is_returned_whole(self):
        solution = {"challenge": "c", "validate": "v", "seccode": "s"}
        solver, _ = _solver(
            _Resp({"errorId": 0, "taskId": 7}),
            _Resp({"errorId": 0, "status": "ready", "solution": solution}),
        )
        assert solver.solve_geetest("gt", "ch", "api.geetest.com") == solution

    def test_geetest_scalar_result_is_wrapped(self):
        solver, _ = _solver(
            _Resp({"errorId": 0, "taskId": 7}),
            _Resp({"errorId": 0, "status": "ready", "solution": {"token": "tok"}}),
        )
        assert solver.solve_geetest("gt", "ch", "api.geetest.com") == {
            "challenge": "ch",
            "validate": "tok",
            "seccode": "",
        }

    def test_missing_key_raises_before_any_request(self, monkeypatch):
        monkeypatch.delenv("ANTICAPTCHA_API_KEY", raising=False)
        solver, session = _solver()
        solver.config.api_key = None
        with pytest.raises(CaptchaSolvingError, match="No anticaptcha API key"):
            solver.solve_recaptcha_v2(SITE_KEY, URL)
        assert session.calls == []

    def test_api_error_id_raises_with_the_description(self):
        solver, _ = _solver(_Resp({"errorId": 1, "errorDescription": "bad key"}))
        with pytest.raises(CaptchaSolvingError, match="bad key"):
            solver.solve_recaptcha_v2(SITE_KEY, URL)

    def test_missing_task_id_raises(self):
        solver, _ = _solver(_Resp({"errorId": 0, "taskId": 0}))
        with pytest.raises(CaptchaSolvingError, match="No taskId"):
            solver.solve_recaptcha_v2(SITE_KEY, URL)

    def test_transport_error_becomes_a_solving_error(self):
        solver, _ = _solver(_Resp({"errorId": 0, "taskId": 7}))
        solver.session.post = lambda *a, **k: (_ for _ in ()).throw(
            requests.ConnectionError("offline")
        )
        with pytest.raises(CaptchaSolvingError, match="Failed to create"):
            solver.solve_recaptcha_v2(SITE_KEY, URL)

    def test_http_error_becomes_a_solving_error(self):
        solver, _ = _solver(_Resp({}, status=500))
        with pytest.raises(CaptchaSolvingError, match="Failed to create"):
            solver.solve_recaptcha_v2(SITE_KEY, URL)


class TestAnticaptchaPolling:
    def test_processing_then_ready(self):
        solver, session = _solver(
            _Resp({"errorId": 0, "taskId": 7}),
            _Resp({"errorId": 0, "status": "processing"}),
            _Resp({"errorId": 0, "status": "processing"}),
            _Resp({"errorId": 0, "status": "ready", "solution": {"text": "plain"}}),
        )
        assert solver.solve_recaptcha_v2(SITE_KEY, URL) == "plain"
        assert len(session.calls) == 4

    def test_timeout_raises(self):
        solver, _ = _solver(
            _Resp({"errorId": 0, "taskId": 7}),
            *[_Resp({"errorId": 0, "status": "processing"})] * 40,
        )
        with pytest.raises(CaptchaSolvingError, match="timeout"):
            solver.solve_recaptcha_v2(SITE_KEY, URL)

    def test_a_poll_error_is_retried(self):
        solver, _ = _solver(
            _Resp({"errorId": 0, "taskId": 7}),
            _Resp({}, status=503),
            _Resp({"errorId": 0, "status": "ready", "solution": {"token": "tok"}}),
        )
        assert solver.solve_recaptcha_v2(SITE_KEY, URL) == "tok"

    def test_an_error_id_during_polling_raises(self):
        solver, _ = _solver(
            _Resp({"errorId": 0, "taskId": 7}),
            _Resp({"errorId": 2, "errorDescription": "quota"}),
        )
        with pytest.raises(CaptchaSolvingError, match="quota"):
            solver.solve_recaptcha_v2(SITE_KEY, URL)


class TestTwoCaptcha:
    def test_recaptcha_v2_is_submitted(self):
        solver, session = _solver(
            _Resp({"status": 1, "request": "42"}),
            _Resp({"status": 1, "request": "TOKEN_OK"}),
            provider=CaptchaProvider.TWOCAPTCHA,
        )
        assert solver.solve_recaptcha_v2(SITE_KEY, URL) == "TOKEN_OK"
        params = session.calls[0][1]["data"]
        assert params["method"] == "userrecaptcha"
        assert params["googlekey"] == SITE_KEY
        assert params["json"] == 1
        assert session.calls[0][0].startswith("https://")

    def test_v3_adds_version_action_and_score(self):
        solver, session = _solver(
            _Resp({"status": 1, "request": "42"}),
            _Resp({"status": 1, "request": "TOKEN_OK"}),
            provider=CaptchaProvider.TWOCAPTCHA,
        )
        solver.solve_recaptcha_v3(SITE_KEY, URL, action="signup", min_score=0.4)
        params = session.calls[0][1]["data"]
        assert (params["version"], params["action"], params["min_score"]) == ("v3", "signup", 0.4)

    def test_invisible_is_only_sent_for_recaptcha(self):
        solver, session = _solver(
            _Resp({"status": 1, "request": "42"}),
            _Resp({"status": 1, "request": "TOKEN_OK"}),
            provider=CaptchaProvider.TWOCAPTCHA,
        )
        solver.solve_recaptcha_v2(SITE_KEY, URL, invisible=True)
        assert session.calls[0][1]["data"]["invisible"] == 1

    def test_submit_rejection_raises(self):
        solver, _ = _solver(
            _Resp({"status": 0, "request": "ERROR_WRONG_USER_KEY"}),
            provider=CaptchaProvider.TWOCAPTCHA,
        )
        with pytest.raises(CaptchaSolvingError, match="WRONG_USER_KEY"):
            solver.solve_recaptcha_v2(SITE_KEY, URL)

    def test_captcha_not_ready_yet_is_polled(self):
        solver, _ = _solver(
            _Resp({"status": 1, "request": "42"}),
            _Resp({"status": 0, "request": "CAPCHA_NOT_READY"}),
            _Resp({"status": 1, "request": "TOKEN_OK"}),
            provider=CaptchaProvider.TWOCAPTCHA,
        )
        assert solver.solve_recaptcha_v2(SITE_KEY, URL) == "TOKEN_OK"

    def test_missing_key_raises(self):
        solver, _ = _solver(provider=CaptchaProvider.TWOCAPTCHA)
        solver.config.api_key = None
        with pytest.raises(CaptchaSolvingError, match="No 2captcha API key"):
            solver.solve_recaptcha_v2(SITE_KEY, URL)


class TestBalance:
    def test_dispatch_follows_the_provider(self, monkeypatch):
        solver, _ = _solver()
        monkeypatch.setattr(solver, "_get_anticaptcha_balance", lambda: 1.5)
        assert solver.get_balance() == 1.5

        solver.config.provider = CaptchaProvider.TWOCAPTCHA
        monkeypatch.setattr(solver, "_get_2captcha_balance", lambda: 2.5)
        assert solver.get_balance() == 2.5


class TestTwoCaptchaVariants:
    def test_hcaptcha_uses_the_hcaptcha_method(self):
        solver, session = _solver(
            _Resp({"status": 1, "request": "4"}),
            _Resp({"status": 1, "request": "TOKEN"}),
            provider=CaptchaProvider.TWOCAPTCHA,
        )
        assert solver.solve_hcaptcha(SITE_KEY, URL) == "TOKEN"
        assert session.calls[0][1]["data"]["method"] == "hcaptcha"

    def test_turnstile_uses_the_turnstile_method(self):
        solver, session = _solver(
            _Resp({"status": 1, "request": "4"}),
            _Resp({"status": 1, "request": "TOKEN"}),
            provider=CaptchaProvider.TWOCAPTCHA,
        )
        assert solver.solve_turnstile(SITE_KEY, URL) == "TOKEN"
        assert session.calls[0][1]["data"]["method"] == "turnstile"

    def test_poll_timeout_raises(self):
        solver, _ = _solver(
            _Resp({"status": 1, "request": "4"}),
            *[_Resp({"status": 0, "request": "CAPCHA_NOT_READY"})] * 40,
            provider=CaptchaProvider.TWOCAPTCHA,
        )
        with pytest.raises(CaptchaSolvingError, match="timeout"):
            solver.solve_recaptcha_v2(SITE_KEY, URL)

    def test_poll_transport_error_is_retried(self):
        solver, _ = _solver(
            _Resp({"status": 1, "request": "4"}),
            _Resp({}, status=502),
            _Resp({"status": 1, "request": "TOKEN"}),
            provider=CaptchaProvider.TWOCAPTCHA,
        )
        assert solver.solve_recaptcha_v2(SITE_KEY, URL) == "TOKEN"


class TestTwoCaptchaGeetest:
    def test_json_solution_is_parsed(self):
        body = '{"challenge": "c2", "validate": "v2", "seccode": "s2"}'
        solver, _ = _solver(
            _Resp({"status": 1, "request": "4"}),
            _Resp({"status": 1, "request": body}),
            provider=CaptchaProvider.TWOCAPTCHA,
        )
        assert solver.solve_geetest("gt", "c1", "api.geetest.com") == {
            "challenge": "c2",
            "validate": "v2",
            "seccode": "s2",
        }

    def test_unparseable_solution_keeps_the_original_challenge(self):
        solver, _ = _solver(
            _Resp({"status": 1, "request": "4"}),
            _Resp({"status": 1, "request": "raw-validate"}),
            provider=CaptchaProvider.TWOCAPTCHA,
        )
        assert solver.solve_geetest("gt", "c1", "api.geetest.com") == {
            "challenge": "c1",
            "validate": "raw-validate",
            "seccode": "",
        }

    def test_geetest_rejection_raises(self):
        solver, _ = _solver(
            _Resp({"status": 0, "request": "ERROR_GT"}),
            provider=CaptchaProvider.TWOCAPTCHA,
        )
        with pytest.raises(CaptchaSolvingError, match="ERROR_GT"):
            solver.solve_geetest("gt", "c1", "api.geetest.com")


class TestBalances:
    def test_anticaptcha_balance(self):
        solver, _ = _solver(_Resp({"errorId": 0, "balance": 12.5}))
        assert solver.get_balance() == 12.5

    def test_anticaptcha_balance_error(self):
        solver, _ = _solver(_Resp({"errorId": 1, "errorDescription": "bad key"}))
        with pytest.raises(CaptchaSolvingError, match="bad key"):
            solver.get_balance()

    def test_anticaptcha_balance_requires_a_key(self, monkeypatch):
        monkeypatch.delenv("ANTICAPTCHA_API_KEY", raising=False)
        solver, _ = _solver()
        solver.config.api_key = None
        with pytest.raises(CaptchaSolvingError, match="No anticaptcha API key"):
            solver.get_balance()

    def test_two_captcha_balance(self):
        solver, session = _solver(
            _Resp({"status": 1, "request": "3.25"}), provider=CaptchaProvider.TWOCAPTCHA
        )
        assert solver.get_balance() == 3.25
        assert session.calls[0][1]["params"]["action"] == "getbalance"

    def test_two_captcha_balance_error(self):
        solver, _ = _solver(
            _Resp({"status": 0, "request": "ERROR_KEY"}), provider=CaptchaProvider.TWOCAPTCHA
        )
        with pytest.raises(CaptchaSolvingError, match="ERROR_KEY"):
            solver.get_balance()

    def test_two_captcha_balance_requires_a_key(self, monkeypatch):
        monkeypatch.delenv("TWOCAPTCHA_API_KEY", raising=False)
        solver, _ = _solver(provider=CaptchaProvider.TWOCAPTCHA)
        solver.config.api_key = None
        with pytest.raises(CaptchaSolvingError, match="No 2captcha API key"):
            solver.get_balance()
