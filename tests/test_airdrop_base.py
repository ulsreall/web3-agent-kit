"""The legacy airdrop platform base: models, session setup and both retry loops.

The sync and async request helpers here carried the same two defects as the
executor helper — a persistent 429 ended in `raise None`, and `Retry-After` went
straight into `int()`. Both are pinned on both paths so they cannot come back in
one and not the other.
"""

from __future__ import annotations

import asyncio
import time

import pytest
import requests

from web3_agent_kit.airdrop import base as airdrop_base
from web3_agent_kit.airdrop.base import (
    AirdropCampaign,
    AirdropTask,
    BaseAirdropPlatform,
    PlatformConfig,
    TaskStatus,
    TaskType,
)


class _Resp:
    def __init__(self, status=200, headers=None):
        self.status_code = status
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code), response=self)


class _Session:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0
        self.headers = {}
        self.cookies = _Jar()
        self.proxies = None

    def request(self, *a, **k):
        self.calls += 1
        item = self._responses[min(self.calls - 1, len(self._responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        pass


class _Jar:
    def __init__(self):
        self.set_calls = []

    def set(self, name, value):
        self.set_calls.append((name, value))


class _Platform(BaseAirdropPlatform):
    platform_name = "unit"

    def __init__(self, responses, **cfg):
        config = PlatformConfig(max_retries=3, retry_delay=0, rate_limit_delay=0, **cfg)
        super().__init__(config)
        # Keep what the base set up on the real session, then swap in a scripted one.
        headers, cookies, proxies = self.session.headers, self.session.cookies, self.session.proxies
        self.session = _Session(responses)
        self.session.headers.update(headers)
        self.session.cookies = cookies
        self.session.proxies = proxies

    def login(self, credentials):
        return True

    def get_tasks(self, campaign_id):
        return []

    def complete_task(self, task):
        return True

    def verify_completion(self, task):
        return True


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(airdrop_base.time, "sleep", lambda s: slept.append(s))
    real_sleep = asyncio.sleep

    async def _async_sleep(_s):
        slept.append(_s)
        await real_sleep(0)

    monkeypatch.setattr(airdrop_base.asyncio, "sleep", _async_sleep)
    return slept


class TestInterface:
    def test_the_session_carries_the_user_agent(self):
        platform = _Platform([_Resp()])
        assert platform.session.headers["User-Agent"] == platform.config.user_agent

    def test_a_session_cookie_is_set(self):
        platform = _Platform([_Resp()], session_cookie="abc")
        assert platform.session.cookies.get("session") == "abc"

    def test_a_proxy_is_applied_to_both_schemes(self):
        platform = _Platform([_Resp()], proxy="http://p:1")
        assert platform.session.proxies == {"http": "http://p:1", "https": "http://p:1"}

    def test_discover_campaigns_defaults_empty(self):
        assert _Platform([_Resp()]).discover_campaigns() == []


class TestModels:
    def test_social_and_on_chain_flags(self):
        assert AirdropTask("1", "p", TaskType.SOCIAL_TWITTER_FOLLOW, "t").is_social is True
        assert AirdropTask("1", "p", TaskType.ON_CHAIN_TX, "t").is_on_chain is True
        assert AirdropTask("1", "p", TaskType.QUIZ, "t").is_social is False

    def test_a_task_defaults_to_pending(self):
        assert AirdropTask("1", "p", TaskType.QUIZ, "t").status is TaskStatus.PENDING

    def test_progress_is_zero_without_points(self):
        assert AirdropCampaign("c", "p", "n").progress == 0.0

    def test_progress_is_a_ratio(self):
        assert AirdropCampaign("c", "p", "n", total_points=10, earned_points=5).progress == 0.5

    def test_a_campaign_without_a_deadline_never_expires(self):
        assert AirdropCampaign("c", "p", "n").is_expired is False

    def test_an_old_deadline_expires(self):
        assert AirdropCampaign("c", "p", "n", deadline=time.time() - 10).is_expired is True

    def test_a_future_deadline_does_not(self):
        assert AirdropCampaign("c", "p", "n", deadline=time.time() + 60).is_expired is False


class TestRateLimit:
    def test_a_recent_call_sleeps(self, no_sleep):
        platform = _Platform([_Resp()])
        platform.config.rate_limit_delay = 2.0
        platform._last_request_time = time.time()
        platform._rate_limit()
        assert no_sleep and no_sleep[0] <= 2.0

    def test_a_600_response_is_retried(self):
        assert _Platform([_Resp(429, {"Retry-After": "1"}), _Resp()])._get("u").status_code == 200

    def test_a_persistent_429_raises_http_error(self):
        with pytest.raises(requests.HTTPError, match="still rate limited after 3"):
            _Platform([_Resp(429)])._get("u")

    def test_a_connection_error_recovers(self):
        assert _Platform([requests.ConnectionError("x"), _Resp()])._get("u").status_code == 200

    def test_exhausted_errors_raise_the_last(self):
        platform = _Platform([requests.ConnectionError("first"), requests.ConnectionError("last")])
        with pytest.raises(requests.ConnectionError, match="last"):
            platform._get("u")

    def test_a_non_requests_error_is_not_retried(self):
        platform = _Platform([RuntimeError("boom"), _Resp()])
        with pytest.raises(RuntimeError):
            platform._get("u")
        assert platform.session.calls == 1

    def test_the_retry_after_header_is_honoured(self, no_sleep):
        _Platform([_Resp(429, {"Retry-After": "3"}), _Resp()])._get("u")
        assert 3.0 in no_sleep

    def test_a_bad_retry_after_falls_back(self, no_sleep):
        _Platform([_Resp(429, {"Retry-After": "soon"}), _Resp()])._get("u")
        assert 3.0 not in no_sleep


class TestAsync:
    def test_an_async_200_returns(self):
        platform = _Platform([_Resp()])
        assert asyncio.run(platform._async_get("u")).status_code == 200

    def test_an_async_persistent_429_raises_http_error(self):
        platform = _Platform([_Resp(429)])
        with pytest.raises(requests.HTTPError, match="still rate limited"):
            asyncio.run(platform._async_get("u"))

    def test_an_async_429_header_is_honoured(self, no_sleep):
        platform = _Platform([_Resp(429, {"Retry-After": "2"}), _Resp()])
        asyncio.run(platform._async_post("u"))
        assert 2.0 in no_sleep

    def test_an_async_connection_error_recovers(self):
        platform = _Platform([requests.ConnectionError("x"), _Resp()])
        assert asyncio.run(platform._async_get("u")).status_code == 200
