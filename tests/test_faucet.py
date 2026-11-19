"""Faucet cooldown bookkeeping and claim orchestration.

Cooldowns are what keep a claim loop from hammering a faucet and getting the
address blocked, so they have to survive a restart and have to be comparable
once loaded. The claim loop decides what is skipped and how results are
recorded.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from web3_agent_kit.airdrop.faucet import ClaimResult, FaucetClaimer, FaucetConfig

WALLET = "0x" + "cd" * 20


@pytest.fixture(autouse=True)
def isolated_cooldown_file(tmp_path, monkeypatch):
    """Point the on-disk cooldown file at the test's tmp dir."""
    target = tmp_path / "cooldowns.json"
    monkeypatch.setattr(
        "web3_agent_kit.airdrop.faucet.Path",
        lambda arg: target if "faucet_cooldowns" in str(arg) else type(target)(arg),
    )
    return target


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("web3_agent_kit.airdrop.faucet.asyncio.sleep", _noop)


async def _noop(*_a, **_k):
    return None


def _faucet(name="F", chain="base_sepolia", cooldown=24) -> FaucetConfig:
    return FaucetConfig(
        name=name,
        chain=chain,
        url="https://faucet.example/claim",
        cooldown_hours=cooldown,
    )


class TestCooldown:
    def test_a_fresh_faucet_is_not_cooling_down(self):
        assert FaucetClaimer()._in_cooldown("x") is False

    def test_a_set_cooldown_blocks(self):
        claimer = FaucetClaimer()
        claimer._set_cooldown("x", 1)
        assert claimer._in_cooldown("x") is True

    def test_a_past_cooldown_does_not_block(self):
        claimer = FaucetClaimer()
        claimer._cooldowns["x"] = datetime.now(timezone.utc) - timedelta(minutes=1)
        assert claimer._in_cooldown("x") is False

    def test_a_cooldown_written_to_disk_is_reloaded(self):
        first = FaucetClaimer()
        first._set_cooldown("x", 2)
        assert FaucetClaimer()._in_cooldown("x") is True

    def test_an_naive_timestamp_does_not_break_the_comparison(self, isolated_cooldown_file):
        # A hand-edited file may omit the offset; comparing naive with aware
        # used to raise TypeError.
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(tzinfo=None)
        isolated_cooldown_file.write_text(json.dumps({"x": future.isoformat()}))
        assert FaucetClaimer()._in_cooldown("x") is True


class TestAvailable:
    def test_cooling_faucets_are_hidden(self):
        claimer = FaucetClaimer()
        claimer._faucets = {"a": _faucet("A"), "b": _faucet("B")}
        claimer._set_cooldown("a", 1)
        assert [f.name for f in claimer.get_available(WALLET)] == ["B"]

    def test_all_faucets_is_a_copy(self):
        claimer = FaucetClaimer()
        claimer.get_all_faucets()["injected"] = _faucet()
        assert "injected" not in claimer._faucets


class _Claimer(FaucetClaimer):
    def __init__(self, outcomes):
        super().__init__()
        self._faucets = {}
        self._outcomes = outcomes

    async def _claim_faucet(self, faucet, wallet):
        ok = self._outcomes[faucet.name]
        return ClaimResult(
            faucet=faucet.name,
            chain=faucet.chain,
            token=faucet.token,
            success=ok,
            amount="0.1" if ok else "",
            error="" if ok else "quota",
        )


class TestClaiming:
    @pytest.mark.asyncio
    async def test_a_success_sets_the_cooldown_and_records_the_result(self):
        claimer = _Claimer({"A": True})
        claimer._faucets = {"a": _faucet("A")}
        results = await claimer.claim_all(WALLET)
        assert results[0].success is True
        assert claimer._in_cooldown("a") is True

    @pytest.mark.asyncio
    async def test_a_failure_does_not_set_a_cooldown(self):
        claimer = _Claimer({"A": False})
        claimer._faucets = {"a": _faucet("A")}
        results = await claimer.claim_all(WALLET)
        assert results[0].success is False
        assert claimer._in_cooldown("a") is False

    @pytest.mark.asyncio
    async def test_a_cooling_faucet_is_recorded_as_skipped(self):
        claimer = _Claimer({"A": True})
        claimer._faucets = {"a": _faucet("A")}
        claimer._set_cooldown("a", 1)
        results = await claimer.claim_all(WALLET)
        assert results[0].error == "In cooldown"

    @pytest.mark.asyncio
    async def test_skip_cooldown_overrides_it(self):
        claimer = _Claimer({"A": True})
        claimer._faucets = {"a": _faucet("A")}
        claimer._set_cooldown("a", 1)
        results = await claimer.claim_all(WALLET, skip_cooldown=True)
        assert results[0].success is True

    @pytest.mark.asyncio
    async def test_a_chain_filter_narrows_the_run(self):
        claimer = _Claimer({"A": True, "B": True})
        claimer._faucets = {"a": _faucet("A", chain="a"), "b": _faucet("B", chain="b")}
        results = await claimer.claim_all(WALLET, chains=["b"])
        assert [r.faucet for r in results] == ["B"]

    @pytest.mark.asyncio
    async def test_results_are_reset_between_runs(self):
        claimer = _Claimer({"A": True})
        claimer._faucets = {"a": _faucet("A")}
        await claimer.claim_all(WALLET)
        await claimer.claim_all(WALLET, skip_cooldown=True)
        assert len(claimer.get_results()) == 1


class TestOutput:
    def test_no_results_message(self):
        assert "No results yet" in FaucetClaimer().print_results()

    def test_summary_counts_success_and_failure(self):
        claimer = FaucetClaimer()
        claimer._results = [
            ClaimResult(faucet="A", chain="c", token="ETH", success=True, amount="0.1"),
            ClaimResult(faucet="B", chain="c", token="ETH", error="quota"),
        ]
        text = claimer.print_results()
        assert "Success: 1" in text
        assert "Failed: 1" in text

    def test_export_returns_json_and_writes_a_file(self, tmp_path):
        claimer = FaucetClaimer()
        claimer._results = [ClaimResult(faucet="A", chain="c", token="ETH", success=True)]
        path = tmp_path / "out.json"
        claimer.export_json(str(path))
        assert json.loads(path.read_text())["results"][0]["faucet"] == "A"


class _Resp:
    def __init__(self, payload=None, status=200, content_type="application/json", text=""):
        self._payload = payload
        self.status_code = status
        self.headers = {"content-type": content_type}
        self.text = text

    def json(self):
        return self._payload


class _Session:
    def __init__(self, resp):
        self._resp = resp
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self._resp

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self._resp


def _run(claimer, faucet):
    import asyncio

    return asyncio.run(claimer._claim_faucet(faucet, WALLET))


class TestClaimRequest:
    def test_the_default_body_carries_the_wallet(self):
        claimer = FaucetClaimer()
        claimer._session = _Session(_Resp({"success": True, "txHash": "0xabc", "amount": "0.5"}))
        result = _run(claimer, _faucet())
        assert claimer._session.calls[0][2]["json"] == {"address": WALLET}
        assert result.success is True
        assert result.tx_hash == "0xabc"
        assert result.amount == "0.5"

    def test_a_template_placeholder_is_substituted(self):
        claimer = FaucetClaimer()
        claimer._session = _Session(_Resp({"success": True}))
        faucet = _faucet()
        faucet.body_template = {"to": "{wallet}", "network": "base"}
        _run(claimer, faucet)
        body = claimer._session.calls[0][2]["json"]
        assert body["to"] == WALLET
        assert body["network"] == "base"

    def test_api_url_wins_over_the_page_url(self):
        claimer = FaucetClaimer()
        claimer._session = _Session(_Resp({"success": True}))
        faucet = _faucet()
        faucet.api_url = "https://api.example/claim"
        _run(claimer, faucet)
        assert claimer._session.calls[0][1] == "https://api.example/claim"

    def test_a_get_faucet_sends_query_params(self):
        claimer = FaucetClaimer()
        claimer._session = _Session(_Resp({"success": True}))
        faucet = _faucet()
        faucet.method = "GET"
        _run(claimer, faucet)
        assert claimer._session.calls[0][0] == "GET"
        assert claimer._session.calls[0][2]["params"] == {"address": WALLET}

    def test_a_failed_claim_reports_no_amount(self):
        claimer = FaucetClaimer()
        claimer._session = _Session(_Resp({"success": False, "error": "quota"}))
        assert _run(claimer, _faucet()).amount == ""

    def test_status_success_counts(self):
        claimer = FaucetClaimer()
        claimer._session = _Session(_Resp({"status": "success"}))
        assert _run(claimer, _faucet()).success is True

    def test_a_plain_text_success_indicator_counts(self):
        claimer = FaucetClaimer()
        claimer._session = _Session(
            _Resp(status=200, content_type="text/html", text="<p>Claim successful</p>")
        )
        assert _run(claimer, _faucet()).success is True

    def test_a_plain_text_body_without_the_indicator_fails(self):
        claimer = FaucetClaimer()
        claimer._session = _Session(_Resp(status=200, content_type="text/html", text="<p>nope"))
        assert _run(claimer, _faucet()).success is False

    def test_an_http_error_records_the_status(self):
        claimer = FaucetClaimer()
        claimer._session = _Session(_Resp(status=429, text="slow down"))
        result = _run(claimer, _faucet())
        assert result.success is False
        assert "429" in result.error

    def test_a_timeout_is_named(self):
        import requests

        claimer = FaucetClaimer()

        def post(*a, **k):
            raise requests.Timeout()

        claimer._session = type("S", (), {"post": staticmethod(post), "get": staticmethod(post)})()
        assert _run(claimer, _faucet()).error == "Request timeout"

    def test_a_captcha_without_a_key_is_sent_anyway(self):
        # No key: the field is simply omitted and the faucet decides.
        claimer = FaucetClaimer()
        claimer._session = _Session(_Resp({"success": True}))
        faucet = _faucet()
        faucet.requires_captcha = True
        _run(claimer, faucet)
        assert "captcha" not in claimer._session.calls[0][2]["json"]

    def test_a_failed_captcha_solve_stops_before_claiming(self, monkeypatch):
        claimer = FaucetClaimer(captcha_api_key="k")

        async def no_token(_faucet):
            return None

        monkeypatch.setattr(claimer, "_solve_captcha", no_token)
        claimer._session = _Session(_Resp({"success": True}))
        faucet = _faucet()
        faucet.requires_captcha = True
        result = _run(claimer, faucet)
        assert result.error == "CAPTCHA solving failed"
        assert claimer._session.calls == []
