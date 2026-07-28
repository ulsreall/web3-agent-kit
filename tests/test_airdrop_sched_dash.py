"""Extra tests for AirdropScheduler and PointsDashboard."""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from web3_agent_kit.airdrop.dashboard import (
    DashboardConfig,
    PlatformPoints,
    PointsDashboard,
    PointsSnapshot,
)
from web3_agent_kit.airdrop.scheduler import (
    AirdropScheduler,
    ExecutionLog,
    ScheduledTask,
    ScheduleFrequency,
    SchedulerConfig,
    TaskExecutionStatus,
)


@pytest.fixture
def tmp_json():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    os.unlink(path)
    yield path
    if os.path.exists(path):
        os.unlink(path)


# ─── Scheduler ───────────────────────────────────────────────────


class TestScheduledTask:
    def test_success_rate_zero(self):
        t = ScheduledTask("id", "n", ScheduleFrequency.DAILY)
        assert t.success_rate == 0.0

    def test_success_rate(self):
        t = ScheduledTask("id", "n", ScheduleFrequency.DAILY)
        t.total_runs = 4
        t.total_successes = 3
        assert t.success_rate == 0.75

    def test_is_due_disabled(self):
        t = ScheduledTask("id", "n", ScheduleFrequency.DAILY, enabled=False)
        assert t.is_due is False

    def test_is_due_no_next_run(self):
        t = ScheduledTask("id", "n", ScheduleFrequency.DAILY)
        assert t.is_due is True

    def test_is_due_past(self):
        t = ScheduledTask("id", "n", ScheduleFrequency.DAILY)
        t.next_run = datetime.now(timezone.utc) - timedelta(hours=1)
        assert t.is_due is True

    def test_is_due_future(self):
        t = ScheduledTask("id", "n", ScheduleFrequency.DAILY)
        t.next_run = datetime.now(timezone.utc) + timedelta(hours=1)
        assert t.is_due is False

    def test_to_dict(self):
        t = ScheduledTask("id", "n", ScheduleFrequency.DAILY, platform="galxe")
        d = t.to_dict()
        assert d["task_id"] == "id"
        assert d["frequency"] == "daily"
        assert d["platform"] == "galxe"
        assert d["success_rate"] == 0.0


class TestSchedulerAdd:
    def test_add_daily(self):
        s = AirdropScheduler()
        t = s.add_daily("t1", "09:00", lambda: None, platform="galxe")
        assert t.frequency == ScheduleFrequency.DAILY
        assert t.target_time == "09:00"
        assert t.next_run is not None
        assert s.get_task("t1") is t

    def test_add_hourly(self):
        s = AirdropScheduler()
        t = s.add_hourly("t2", lambda: None)
        assert t.frequency == ScheduleFrequency.HOURLY
        assert t.next_run is not None

    def test_add_weekly(self):
        s = AirdropScheduler()
        t = s.add_weekly("t3", 2, "10:00", lambda: None)
        assert t.frequency == ScheduleFrequency.WEEKLY
        assert t.next_run is not None

    def test_add_custom(self):
        s = AirdropScheduler()
        t = s.add_custom("t4", 30.0, lambda: None)
        assert t.frequency == ScheduleFrequency.CUSTOM
        assert t.metadata["interval_seconds"] == 30.0


class TestSchedulerManage:
    def test_remove(self):
        s = AirdropScheduler()
        s.add_daily("t1", "09:00", lambda: None)
        assert s.remove_task("t1") is True
        assert s.remove_task("t1") is False

    def test_enable_disable(self):
        s = AirdropScheduler()
        s.add_daily("t1", "09:00", lambda: None)
        assert s.disable_task("t1") is True
        assert s.get_task("t1").enabled is False
        assert s.enable_task("t1") is True
        assert s.get_task("t1").enabled is True
        assert s.enable_task("missing") is False
        assert s.disable_task("missing") is False

    def test_get_all_and_due(self):
        s = AirdropScheduler()
        s.add_daily("t1", "09:00", lambda: None)
        t2 = s.add_daily("t2", "10:00", lambda: None)
        t2.next_run = datetime.now(timezone.utc) + timedelta(days=1)
        assert len(s.get_all_tasks()) == 2
        due_ids = [t.task_id for t in s.get_due_tasks()]
        assert "t1" not in due_ids or "t2" not in due_ids

    def test_get_summary(self):
        s = AirdropScheduler()
        s.add_daily("t1", "09:00", lambda: None)
        s.add_daily("t2", "10:00", lambda: None, enabled=False)
        summary = s.get_summary()
        assert summary["total_tasks"] == 2
        assert summary["enabled_tasks"] == 1
        assert summary["disabled_tasks"] == 1


class TestSchedulerExecution:
    def test_run_task_now_success(self):
        s = AirdropScheduler()
        cb = MagicMock(return_value="ok")
        s.add_daily("t1", "09:00", cb)
        log = asyncio.run(s.run_task_now("t1"))
        assert log.status == TaskExecutionStatus.SUCCESS
        assert log.result == "ok"
        assert s.get_task("t1").total_successes == 1
        cb.assert_called_once()

    def test_run_task_now_missing(self):
        s = AirdropScheduler()
        assert asyncio.run(s.run_task_now("nope")) is None

    def test_run_task_no_callback(self):
        s = AirdropScheduler()
        s._tasks["t1"] = ScheduledTask("t1", "n", ScheduleFrequency.DAILY)
        log = asyncio.run(s.run_task_now("t1"))
        assert log.status == TaskExecutionStatus.SKIPPED

    def test_run_task_failure(self):
        s = AirdropScheduler()
        cb = MagicMock(side_effect=RuntimeError("boom"))
        # retry_delay 0 to keep test fast; max_retries 2
        s.add_daily("t1", "09:00", cb, max_retries=2)
        s.get_task("t1").retry_delay = 0
        log = asyncio.run(s.run_task_now("t1"))
        assert log.status == TaskExecutionStatus.FAILED
        assert "boom" in log.error
        assert s.get_task("t1").consecutive_failures == 2

    def test_execution_log_filter(self):
        s = AirdropScheduler()
        s.add_daily("t1", "09:00", MagicMock(return_value=1))
        s.add_daily("t2", "09:00", MagicMock(return_value=2))
        asyncio.run(s.run_task_now("t1"))
        asyncio.run(s.run_task_now("t2"))
        assert len(s.get_execution_log()) == 2
        assert len(s.get_execution_log(task_id="t1")) == 1


class TestSchedulerCalc:
    def test_next_run_daily(self):
        s = AirdropScheduler()
        nr = s._calculate_next_run(ScheduleFrequency.DAILY, "09:00")
        assert nr.hour == 9 and nr.minute == 0

    def test_next_run_hourly(self):
        s = AirdropScheduler()
        nr = s._calculate_next_run(ScheduleFrequency.HOURLY)
        assert nr > datetime.now(timezone.utc)

    def test_next_run_custom(self):
        s = AirdropScheduler()
        nr = s._calculate_next_run(ScheduleFrequency.CUSTOM)
        assert nr > datetime.now(timezone.utc)

    def test_next_weekly(self):
        s = AirdropScheduler()
        nr = s._calculate_next_weekly(0, "08:30")
        assert nr.hour == 8 and nr.minute == 30
        assert nr > datetime.now(timezone.utc)


class TestSchedulerPersistence:
    def test_export_state(self, tmp_json):
        s = AirdropScheduler()
        s.add_daily("t1", "09:00", lambda: None)
        s.export_state(tmp_json)
        data = json.loads(open(tmp_json).read())
        assert "t1" in data["tasks"]

    def test_save_state_configured(self, tmp_json):
        s = AirdropScheduler(SchedulerConfig(state_path=tmp_json))
        s.add_daily("t1", "09:00", lambda: None)
        s._save_state()
        assert os.path.exists(tmp_json)
        data = json.loads(open(tmp_json).read())
        assert "t1" in data["tasks"]

    def test_load_state(self, tmp_json):
        with open(tmp_json, "w") as f:
            json.dump({"tasks": {"a": {}, "b": {}}}, f)
        # Should load without raising
        s = AirdropScheduler(SchedulerConfig(state_path=tmp_json))
        assert s is not None

    def test_load_state_corrupt(self, tmp_json):
        with open(tmp_json, "w") as f:
            f.write("bad json {{{")
        s = AirdropScheduler(SchedulerConfig(state_path=tmp_json))
        assert s is not None

    def test_log_execution_to_file(self, tmp_json):
        s = AirdropScheduler(SchedulerConfig(log_path=tmp_json))
        log = ExecutionLog(
            task_id="t1", started_at=datetime.now(timezone.utc)
        )
        log.finished_at = datetime.now(timezone.utc)
        s._log_execution(log)
        assert os.path.exists(tmp_json)
        assert "t1" in open(tmp_json).read()

    def test_execution_log_to_dict(self):
        log = ExecutionLog(
            task_id="t1", started_at=datetime.now(timezone.utc)
        )
        d = log.to_dict()
        assert d["task_id"] == "t1"
        assert d["finished_at"] is None


# ─── Dashboard ───────────────────────────────────────────────────


class TestPlatformPoints:
    def test_total_with_referrals(self):
        p = PlatformPoints("galxe", points=100, referral_points=25)
        assert p.total_with_referrals == 125

    def test_to_dict(self):
        p = PlatformPoints("galxe", points=100, rank=5, tier="gold")
        d = p.to_dict()
        assert d["platform"] == "galxe"
        assert d["points"] == 100
        assert d["last_activity"] is None


class TestPointsSnapshot:
    def test_totals(self):
        snap = PointsSnapshot(
            timestamp=datetime.now(timezone.utc),
            platforms={
                "galxe": PlatformPoints("galxe", points=100,
                                        campaigns_completed=3),
                "layer3": PlatformPoints("layer3", points=50,
                                         campaigns_completed=1),
            },
        )
        assert snap.total_points == 150
        assert snap.total_campaigns == 4
        assert snap.to_dict()["total_points"] == 150


class TestDashboardSync:
    def test_sync_requires_wallet(self):
        d = PointsDashboard()
        with pytest.raises(ValueError, match="Wallet address required"):
            d.sync_all()

    def test_sync_all_with_mocked_syncers(self):
        cfg = DashboardConfig(platforms=["galxe", "zealy"])
        d = PointsDashboard(cfg)
        d._sync_galxe = MagicMock(
            return_value=PlatformPoints("galxe", points=500)
        )
        d._sync_zealy = MagicMock(
            return_value=PlatformPoints("zealy", points=0)
        )
        snap = d.sync_all(wallet="0xABC")
        assert snap.total_points == 500
        assert d.get_current() is snap

    def test_sync_skips_unknown_platform(self):
        cfg = DashboardConfig(platforms=["unknown_platform"])
        d = PointsDashboard(cfg)
        snap = d.sync_all(wallet="0xABC")
        assert snap.total_points == 0

    def test_sync_handles_syncer_error(self):
        cfg = DashboardConfig(platforms=["galxe"])
        d = PointsDashboard(cfg)
        d._sync_galxe = MagicMock(side_effect=RuntimeError("api down"))
        snap = d.sync_all(wallet="0xABC")
        assert snap.total_points == 0


class TestDashboardSyncers:
    def test_sync_galxe(self):
        d = PointsDashboard()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "data": {
                "user": {
                    "galxeScore": {"score": 1200, "rank": 42},
                    "participatedCampaignCount": 7,
                }
            }
        }
        d.session.post = MagicMock(return_value=resp)
        pts = d._sync_galxe("0xABC")
        assert pts.points == 1200
        assert pts.rank == 42
        assert pts.campaigns_completed == 7

    def test_sync_galxe_error(self):
        d = PointsDashboard()
        d.session.post = MagicMock(side_effect=RuntimeError("net"))
        assert d._sync_galxe("0xABC") is None

    def test_sync_layer3(self):
        d = PointsDashboard()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"xp": 300, "questsCompleted": 5}
        d.session.get = MagicMock(return_value=resp)
        pts = d._sync_layer3("0xABC")
        assert pts.points == 300
        assert pts.campaigns_completed == 5

    def test_sync_layer3_non_200(self):
        d = PointsDashboard()
        resp = MagicMock()
        resp.status_code = 404
        d.session.get = MagicMock(return_value=resp)
        assert d._sync_layer3("0xABC") is None

    def test_stub_syncers(self):
        d = PointsDashboard()
        assert d._sync_zealy("0xA").platform == "zealy"
        assert d._sync_questn("0xA").platform == "questn"
        assert d._sync_taskon("0xA").platform == "taskon"
        assert d._sync_intract("0xA").platform == "intract"
        assert d._sync_port3("0xA").platform == "port3"


class TestDashboardReporting:
    def _synced(self):
        d = PointsDashboard(DashboardConfig(wallet_address="0xABCDEF0123456789"))
        d._current = PointsSnapshot(
            timestamp=datetime.now(timezone.utc),
            platforms={
                "galxe": PlatformPoints("galxe", points=1500, rank=10,
                                        campaigns_completed=5, streak_days=3),
                "layer3": PlatformPoints("layer3", points=800,
                                         campaigns_completed=2),
            },
        )
        return d

    def test_get_history(self):
        d = self._synced()
        d._history = [d._current, d._current]
        assert len(d.get_history()) == 2
        assert len(d.get_history(limit=1)) == 1

    def test_get_growth_insufficient(self):
        d = PointsDashboard()
        assert d.get_growth()["total_delta"] == 0

    def test_get_growth(self):
        d = PointsDashboard()
        old = PointsSnapshot(
            timestamp=datetime.now(timezone.utc) - timedelta(days=10),
            platforms={"galxe": PlatformPoints("galxe", points=100)},
        )
        new = PointsSnapshot(
            timestamp=datetime.now(timezone.utc),
            platforms={"galxe": PlatformPoints("galxe", points=250)},
        )
        d._history = [old, new]
        growth = d.get_growth(days=30)
        assert growth["total_delta"] == 150
        assert growth["platforms"]["galxe"]["delta"] == 150

    def test_leaderboard_position(self):
        d = self._synced()
        positions = d.get_leaderboard_position()
        assert positions[0]["platform"] == "galxe"
        assert positions[0]["points"] == 1500

    def test_leaderboard_no_data(self):
        d = PointsDashboard()
        assert d.get_leaderboard_position() == []

    def test_print_summary_not_synced(self):
        d = PointsDashboard()
        assert "Not synced" in d.print_summary()

    def test_print_summary(self, capsys):
        d = self._synced()
        out = d.print_summary()
        assert "DASHBOARD" in out

    def test_export_json(self, tmp_json):
        d = self._synced()
        js = d.export_json(tmp_json)
        assert os.path.exists(tmp_json)
        data = json.loads(js)
        assert data["current"]["total_points"] == 2300

    def test_export_markdown(self, tmp_json):
        d = self._synced()
        md = d.export_markdown(tmp_json)
        assert "Airdrop Points Report" in md
        assert os.path.exists(tmp_json)

    def test_export_markdown_no_data(self):
        d = PointsDashboard()
        assert "No data" in d.export_markdown()


class TestDashboardPersistence:
    def test_save_and_load_history(self, tmp_json):
        cfg = DashboardConfig(
            wallet_address="0xABC", history_path=tmp_json,
            platforms=["galxe"],
        )
        d = PointsDashboard(cfg)
        d._sync_galxe = MagicMock(
            return_value=PlatformPoints("galxe", points=999,
                                        campaigns_completed=1)
        )
        d.sync_all(wallet="0xABC")
        assert os.path.exists(tmp_json)
        # New dashboard loads history
        d2 = PointsDashboard(cfg)
        assert len(d2._history) == 1
        assert d2._history[0].total_points == 999

    def test_load_history_corrupt(self, tmp_json):
        with open(tmp_json, "w") as f:
            f.write("not json {{{")
        cfg = DashboardConfig(history_path=tmp_json)
        d = PointsDashboard(cfg)
        assert d._history == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
