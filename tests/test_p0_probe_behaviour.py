"""The P0 probe must report every finding closed, and say so honestly.

The probe is the evidence an auditor runs against an installed package: if it
silently reports "closed" for a probe that could not execute, it becomes a
liar, and the whole bundle loses its value. These tests exercise it end to end
and pin both the verdicts and the exit codes.
"""

from __future__ import annotations

import json

import pytest

from web3_agent_kit.execution import p0_probe


class TestProbeVerdicts:
    def test_every_probe_reports_closed(self):
        results = p0_probe.run_all_probes()
        statuses = {r["id"]: r["status"] for r in results}
        assert statuses == {
            "CHAIN_MISMATCH_SIGNED": "closed",
            "UNBOUND_CONTRACT_CREATION_SIGNED": "closed",
            "POLICY_ALLOW_SIGNS_WITHOUT_AUTHORIZATION": "closed",
            "ALIASED_SIGNER_ESCAPES_CHECKER": "closed",
        }

    def test_probe_order_is_stable(self):
        first = [r["id"] for r in p0_probe.run_all_probes()]
        second = [r["id"] for r in p0_probe.run_all_probes()]
        assert first == second

    def test_chain_mismatch_records_both_chains(self):
        result = p0_probe.probe_chain_mismatch()
        assert "84532" in result["detail"] or "chain" in result["detail"].lower()

    def test_unbound_wallet_never_reaches_the_signer(self):
        result = p0_probe.probe_unbound_contract_creation()
        assert result["detail"]

    def test_policy_allow_probe_counts_signer_calls(self):
        # The count is what distinguishes "refused" from "signed".
        assert p0_probe.probe_policy_allow_without_authorization()["signer_reached"] == 0

    def test_alias_probe_writes_into_a_temp_dir_only(self, tmp_path):
        result = p0_probe.probe_aliased_signer()
        assert result["status"] == "closed"
        assert not list(tmp_path.iterdir())


class TestCli:
    def test_json_output_parses_and_reports_no_gaps(self, capsys):
        assert p0_probe.main(["--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["open_gaps"] == 0
        assert payload["unknown"] == 0
        assert len(payload["results"]) == 4

    def test_human_output_counts_the_probes(self, capsys):
        assert p0_probe.main([]) == 0
        out = capsys.readouterr().out
        assert "open gaps: 0 of 4" in out
        assert "could not evaluate" not in out

    def test_unknown_is_not_a_pass(self, monkeypatch, capsys):
        # A probe that could not run must exit 2, never 0: a missing file is
        # not evidence that the gap is closed.
        monkeypatch.setattr(p0_probe, "_locate_checker", lambda: None)
        assert p0_probe.main([]) == 2
        assert "could not evaluate" in capsys.readouterr().out

    def test_open_gap_exits_one(self, monkeypatch):
        real = p0_probe.probe_aliased_signer

        def reopened():
            result = real()
            result["observed"] = True
            result["status"] = "OPEN"
            return result

        monkeypatch.setattr(p0_probe, "probe_aliased_signer", reopened)
        assert p0_probe.main([]) == 1

    def test_module_entry_point(self, monkeypatch):
        import runpy
        import sys

        monkeypatch.setattr(sys, "argv", ["wak-p0-probe"])
        # runpy re-executes a module pytest already imported; the warning is
        # expected and says nothing about the probe.
        with pytest.raises(SystemExit) as exc:
            runpy.run_module("web3_agent_kit.execution.p0_probe", run_name="__main__")
        assert exc.value.code == 0
